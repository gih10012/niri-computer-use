//! Persistent evdev keyboard for shortcuts. Unlike a per-call wtype keymap,
//! this keeps toolkit shortcut lookup on the compositor's normal keymap.
use anyhow::Result;
use evdev::{uinput::VirtualDevice, AttributeSet, EventType, InputEvent, KeyCode};
use std::{thread::sleep, time::Duration};

pub(crate) struct Keyboard {
    device: VirtualDevice,
}

impl Keyboard {
    pub(crate) fn create() -> Result<Self> {
        let keys: AttributeSet<KeyCode> = (1..=255).map(KeyCode::new).collect();
        let device = VirtualDevice::builder()?
            .name("niri-computer-use-keyboard")
            .with_keys(&keys)?
            .build()?;
        sleep(Duration::from_millis(250));
        Ok(Self { device })
    }

    pub(crate) fn chord(&mut self, modifiers: &[u16], key: u16) -> Result<()> {
        let result = (|| {
            for code in modifiers {
                self.emit(*code, 1)?;
            }
            sleep(Duration::from_millis(30));
            self.emit(key, 1)?;
            sleep(Duration::from_millis(30));
            Ok(())
        })();
        // Always release keys, including after a failed emit.
        let mut release = self.emit(key, 0);
        for code in modifiers.iter().rev() {
            if let Err(error) = self.emit(*code, 0) {
                release = Err(error);
            }
        }
        sleep(Duration::from_millis(40));
        result.and(release)
    }

    fn emit(&mut self, key: u16, value: i32) -> Result<()> {
        self.device
            .emit(&[InputEvent::new_now(EventType::KEY.0, key, value)])?;
        Ok(())
    }
}
