//! Isolated clipboard helper. The single-threaded process forks a foreground
//! data source; it must not fork inside the async MCP host.
use anyhow::{bail, Context, Result};
use base64::{engine::general_purpose::STANDARD, Engine};
use serde::{Deserialize, Serialize};
use std::io::{self, Read};
use wl_clipboard_rs::{copy, paste};

const LIMIT: usize = 16 * 1024 * 1024;

#[derive(Serialize, Deserialize)]
struct Offer {
    mime: String,
    data: String,
}

fn main() -> Result<()> {
    computer_use_linux::diagnostics::hydrate_session_bus_env();
    match std::env::args().nth(1).as_deref() {
        Some("snapshot") => {
            let types = match paste::get_mime_types(
                paste::ClipboardType::Regular,
                paste::Seat::Unspecified,
            ) {
                Ok(types) => types,
                Err(paste::Error::ClipboardEmpty) => {
                    println!("[]");
                    return Ok(());
                }
                Err(error) => return Err(error.into()),
            };
            if types.len() > 64 {
                bail!("clipboard has more than 64 formats");
            }
            let mut types: Vec<_> = types.into_iter().collect();
            types.sort();
            let mut offers = Vec::new();
            let mut total = 0;
            for mime in types {
                let (pipe, _) = paste::get_contents(
                    paste::ClipboardType::Regular,
                    paste::Seat::Unspecified,
                    paste::MimeType::Specific(&mime),
                )?;
                let mut data = Vec::new();
                pipe.take((LIMIT - total + 1) as u64)
                    .read_to_end(&mut data)?;
                total += data.len();
                if total > LIMIT {
                    bail!("clipboard exceeds 16 MiB; refusing to overwrite it");
                }
                offers.push(Offer {
                    mime,
                    data: STANDARD.encode(data),
                });
            }
            println!("{}", serde_json::to_string(&offers)?);
        }
        Some("offer") => {
            let mut input = Vec::new();
            io::stdin()
                .take((LIMIT * 2 + 1) as u64)
                .read_to_end(&mut input)?;
            if input.len() > LIMIT * 2 {
                bail!("clipboard request too large");
            }
            let offers: Vec<Offer> = serde_json::from_slice(&input)?;
            if offers.is_empty() {
                copy::clear(copy::ClipboardType::Regular, copy::Seat::All)?;
            } else {
                let sources = offers
                    .into_iter()
                    .map(|offer| {
                        Ok(copy::MimeSource {
                            source: copy::Source::Bytes(
                                STANDARD
                                    .decode(offer.data)
                                    .context("invalid clipboard base64")?
                                    .into(),
                            ),
                            mime_type: copy::MimeType::Specific(offer.mime),
                        })
                    })
                    .collect::<Result<Vec<_>>>()?;
                let mut options = copy::Options::new();
                options
                    .foreground(true)
                    .omit_additional_text_mime_types(true);
                let prepared = options.prepare_copy_multi(sources)?;
                // This executable is single-threaded. Fork only here, never
                // inside the async MCP server. Do not run parent destructors
                // against the duplicated Wayland connection.
                let pid = unsafe { libc::fork() };
                if pid < 0 {
                    return Err(io::Error::last_os_error().into());
                }
                if pid > 0 {
                    unsafe { libc::_exit(0) };
                }
                if unsafe { libc::daemon(0, 0) } != 0 {
                    return Err(io::Error::last_os_error().into());
                }
                prepared.serve()?;
            }
        }
        _ => bail!("usage: niri-clipboard snapshot | offer (JSON on stdin)"),
    }
    Ok(())
}
