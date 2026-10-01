//! Native Wayland pointer. Extents use the captured image's coordinate space,
//! so absolute motion remains normalized even on fractional-scale displays.
use anyhow::{Context, Result};
use std::{
    sync::OnceLock,
    thread::sleep,
    time::{Duration, Instant},
};
use wayland_client::{
    delegate_noop,
    globals::{registry_queue_init, GlobalListContents},
    protocol::{wl_pointer, wl_registry},
    Connection, Dispatch, EventQueue, QueueHandle,
};
use wayland_protocols_wlr::virtual_pointer::v1::client::{
    zwlr_virtual_pointer_manager_v1::ZwlrVirtualPointerManagerV1,
    zwlr_virtual_pointer_v1::ZwlrVirtualPointerV1,
};

#[derive(Clone)]
pub(crate) enum Operation {
    Click {
        x: i32,
        y: i32,
        button: u32,
        count: u32,
    },
    Drag {
        start: (i32, i32),
        end: (i32, i32),
    },
    Scroll {
        point: Option<(i32, i32)>,
        dx: i32,
        dy: i32,
    },
}
struct State;
impl Dispatch<wl_registry::WlRegistry, GlobalListContents> for State {
    fn event(
        _: &mut Self,
        _: &wl_registry::WlRegistry,
        _: wl_registry::Event,
        _: &GlobalListContents,
        _: &Connection,
        _: &QueueHandle<Self>,
    ) {
    }
}
delegate_noop!(State: ignore ZwlrVirtualPointerManagerV1);
delegate_noop!(State: ignore ZwlrVirtualPointerV1);

struct Pointer {
    queue: EventQueue<State>,
    pointer: ZwlrVirtualPointerV1,
    width: u32,
    height: u32,
}
pub(crate) fn available() -> Result<()> {
    let conn = Connection::connect_to_env()?;
    let (globals, queue) = registry_queue_init::<State>(&conn)?;
    let _: ZwlrVirtualPointerManagerV1 = globals.bind(&queue.handle(), 1..=2, ())?;
    Ok(())
}
fn now() -> u32 {
    static START: OnceLock<Instant> = OnceLock::new();
    START.get_or_init(Instant::now).elapsed().as_millis() as u32
}
impl Pointer {
    fn frame(&mut self) -> Result<()> {
        self.pointer.frame();
        self.queue
            .roundtrip(&mut State)
            .context("virtual pointer roundtrip")?;
        Ok(())
    }
    fn move_to(&mut self, x: i32, y: i32) -> Result<()> {
        self.pointer.motion_absolute(
            now(),
            x.clamp(0, self.width as i32 - 1) as u32,
            y.clamp(0, self.height as i32 - 1) as u32,
            self.width,
            self.height,
        );
        self.frame()?;
        sleep(Duration::from_millis(30));
        Ok(())
    }
    fn button(&mut self, code: u32, pressed: bool) -> Result<()> {
        self.pointer.button(
            now(),
            code,
            if pressed {
                wl_pointer::ButtonState::Pressed
            } else {
                wl_pointer::ButtonState::Released
            },
        );
        self.frame()?;
        sleep(Duration::from_millis(40));
        Ok(())
    }
}

pub(crate) fn run(width: u32, height: u32, operation: Operation) -> Result<()> {
    anyhow::ensure!(width > 0 && height > 0, "empty capture coordinate space");
    let conn = Connection::connect_to_env().context("connect to niri Wayland socket")?;
    let (globals, queue) = registry_queue_init::<State>(&conn)?;
    let qh = queue.handle();
    let manager: ZwlrVirtualPointerManagerV1 = globals
        .bind(&qh, 1..=2, ())
        .context("niri virtual-pointer protocol unavailable")?;
    let pointer = manager.create_virtual_pointer(None, &qh, ());
    let mut pointer = Pointer {
        queue,
        pointer,
        width,
        height,
    };
    match operation {
        Operation::Click {
            x,
            y,
            button,
            count,
        } => {
            pointer.move_to(x, y)?;
            for _ in 0..count.clamp(1, 10) {
                let result = pointer.button(button, true);
                let release = pointer.button(button, false);
                result.and(release)?;
            }
        }
        Operation::Drag { start, end } => {
            pointer.move_to(start.0, start.1)?;
            let result = (|| {
                pointer.button(0x110, true)?;
                for step in 1..=20 {
                    let x = start.0 as i64 + (end.0 as i64 - start.0 as i64) * step / 20;
                    let y = start.1 as i64 + (end.1 as i64 - start.1 as i64) * step / 20;
                    pointer.move_to(x as i32, y as i32)?;
                }
                Ok(())
            })();
            let release = pointer.button(0x110, false);
            result.and(release)?;
        }
        Operation::Scroll { point, dx, dy } => {
            if let Some((x, y)) = point {
                pointer.move_to(x, y)?;
            }
            pointer.pointer.axis_source(wl_pointer::AxisSource::Wheel);
            if dx != 0 {
                pointer.pointer.axis_discrete(
                    now(),
                    wl_pointer::Axis::HorizontalScroll,
                    dx as f64 * 15.0,
                    dx,
                );
            }
            if dy != 0 {
                pointer.pointer.axis_discrete(
                    now(),
                    wl_pointer::Axis::VerticalScroll,
                    dy as f64 * 15.0,
                    dy,
                );
            }
            pointer.frame()?;
            sleep(Duration::from_millis(60));
        }
    }
    pointer.pointer.destroy();
    pointer.queue.roundtrip(&mut State)?;
    Ok(())
}
