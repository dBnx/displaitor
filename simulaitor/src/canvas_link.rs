//! Loopback-only simulator transport using exactly the firmware's wire endpoint.
use displaitor::{Engine, canvas_protocol::Endpoint};
use std::{
    io::{self, Read, Write},
    net::{SocketAddr, TcpListener, TcpStream},
};

pub struct CanvasLink {
    listener: TcpListener,
    client: Option<TcpStream>,
    endpoint: Endpoint,
}

impl CanvasLink {
    pub fn bind(address: &str) -> Result<Self, String> {
        let address: SocketAddr = address
            .parse()
            .map_err(|_| "--canvas-listen requires an IP:port")?;
        if !address.ip().is_loopback() {
            return Err("Canvas simulator listener must use a loopback IP".into());
        }
        let listener = TcpListener::bind(address).map_err(|e| e.to_string())?;
        listener.set_nonblocking(true).map_err(|e| e.to_string())?;
        println!(
            "Canvas listening on {}",
            listener.local_addr().map_err(|e| e.to_string())?
        );
        Ok(Self {
            listener,
            client: None,
            endpoint: Endpoint::new(),
        })
    }

    pub fn service(&mut self, engine: &mut Engine) -> Result<(), String> {
        if self.client.is_none() {
            match self.listener.accept() {
                Ok((client, _)) => {
                    client.set_nonblocking(true).map_err(|e| e.to_string())?;
                    client.set_nodelay(true).map_err(|e| e.to_string())?;
                    self.endpoint.reset(engine.canvas_mut());
                    self.client = Some(client);
                }
                Err(e) if e.kind() == io::ErrorKind::WouldBlock => return Ok(()),
                Err(e) => return Err(e.to_string()),
            }
        }
        let client = self.client.as_mut().expect("accepted client");
        let mut disconnected = false;
        if !self.endpoint.pending().is_empty() {
            match client.write(self.endpoint.pending()) {
                Ok(0) => disconnected = true,
                Ok(count) => self.endpoint.written(count),
                Err(e) if e.kind() == io::ErrorKind::WouldBlock => {}
                Err(_) => disconnected = true,
            }
        } else {
            for _ in 0..512 {
                let mut byte = [0];
                match client.read(&mut byte) {
                    Ok(0) => {
                        disconnected = true;
                        break;
                    }
                    Ok(_) => {
                        self.endpoint.receive(byte[0], engine.canvas_mut());
                        if self.endpoint.take_show_request() {
                            engine.request_canvas();
                        }
                    }
                    Err(e) if e.kind() == io::ErrorKind::WouldBlock => break,
                    Err(_) => {
                        disconnected = true;
                        break;
                    }
                }
                if !self.endpoint.pending().is_empty() {
                    break;
                }
            }
        }
        if disconnected {
            self.client = None;
            self.endpoint.reset(engine.canvas_mut());
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use displaitor::{AppId, AudioId, Controls, Screen, canvas_protocol};
    use std::time::{Duration, Instant};

    fn send(
        link: &mut CanvasLink,
        engine: &mut Engine,
        client: &mut TcpStream,
        command: u8,
        payload: &[u8],
    ) {
        let mut raw = vec![1, command, 0, 0];
        raw.extend_from_slice(payload);
        raw.extend(canvas_protocol::crc32(&raw).to_le_bytes());
        let mut wire = [0; 64];
        let len = canvas_protocol::encode(&raw, &mut wire).unwrap();
        client.write_all(&wire[..len]).unwrap();
        let deadline = Instant::now() + Duration::from_secs(1);
        while link.endpoint.pending().is_empty() {
            assert!(
                Instant::now() < deadline,
                "loopback request was not received"
            );
            link.service(engine).unwrap();
            std::thread::yield_now();
        }
        while !link.endpoint.pending().is_empty() {
            assert!(Instant::now() < deadline, "loopback reply was not drained");
            link.service(engine).unwrap();
        }
    }

    #[test]
    fn loopback_show_opens_canvas_from_another_screen_only_on_explicit_command() {
        let mut link = CanvasLink::bind("127.0.0.1:0").unwrap();
        let mut client = TcpStream::connect(link.listener.local_addr().unwrap()).unwrap();
        let mut engine = Engine::new();
        // Initial and ordinary scene updates retain the starting Splash screen.
        send(&mut link, &mut engine, &mut client, 5, &[0, 0xf8]);
        let _ = engine.update(Duration::ZERO, Controls::default());
        assert_eq!(engine.screen(), Screen::Splash);
        send(&mut link, &mut engine, &mut client, 6, &[]);
        let update = engine.update(Duration::ZERO, Controls::default());
        assert_eq!(engine.screen(), Screen::App(AppId::Canvas));
        assert!(update.redraw);
        assert_eq!(update.audio, Some(AudioId::Stop));
    }

    #[test]
    fn disconnect_aborts_staged_scene_and_deferred_activation() {
        let mut link = CanvasLink::bind("127.0.0.1:0").unwrap();
        let address = link.listener.local_addr().unwrap();
        let mut client = TcpStream::connect(address).unwrap();
        let mut engine = Engine::new();
        send(&mut link, &mut engine, &mut client, 7, &[]);
        send(&mut link, &mut engine, &mut client, 5, &[0, 0xf8]);
        send(&mut link, &mut engine, &mut client, 6, &[]);
        let _ = engine.update(Duration::ZERO, Controls::default());
        assert_eq!(engine.screen(), Screen::Splash);
        drop(client);
        let deadline = Instant::now() + Duration::from_secs(1);
        while link.client.is_some() {
            assert!(Instant::now() < deadline);
            link.service(&mut engine).unwrap();
            std::thread::yield_now();
        }
        let mut client = TcpStream::connect(address).unwrap();
        // Commit cannot resurrect staging from the preceding client session.
        send(&mut link, &mut engine, &mut client, 8, &[]);
        assert_eq!(
            engine.canvas_mut().apply(8, &[]),
            Err(displaitor::canvas::Error::Transaction)
        );
        assert!(!link.endpoint.take_show_request());
        let _ = engine.update(Duration::ZERO, Controls::default());
        assert_eq!(engine.screen(), Screen::Splash);
    }
}
