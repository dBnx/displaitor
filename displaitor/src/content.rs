use crate::{
    AppId,
    navigation::{Action, Entry, Menu, MenuId},
};

pub(crate) const ROOT: MenuId = MenuId::new(0);
pub(crate) const WATCH: MenuId = MenuId::new(1);
pub(crate) const PLAY: MenuId = MenuId::new(2);
const ROOT_ENTRIES: [Entry<'static>; 4] = [
    Entry::new("Names", Action::App(AppId::Names)),
    Entry::new("Watch", Action::Menu(WATCH)),
    Entry::new("Play", Action::Menu(PLAY)),
    Entry::new("Canvas", Action::App(AppId::Canvas)),
];
const WATCH_ENTRIES: [Entry<'static>; 3] = [
    Entry::new("Nyankatz", Action::App(AppId::Nyan)),
    Entry::new("Hyperspace", Action::App(AppId::Hyper)),
    Entry::new("Campfire", Action::App(AppId::Fire)),
];
const PLAY_ENTRIES: [Entry<'static>; 2] = [
    Entry::new("Pong", Action::App(AppId::Pong)),
    Entry::new("Snake", Action::App(AppId::Snake)),
];
pub(crate) static MENUS: [Menu<'static>; 3] = [
    Menu::new("DISPLAITOR", None, &ROOT_ENTRIES),
    Menu::new("WATCH", Some(ROOT), &WATCH_ENTRIES),
    Menu::new("PLAY", Some(ROOT), &PLAY_ENTRIES),
];

// Parse names and measure character widths at compile time, not on each frame.
const NAMES_SOURCE: &str = include_str!(concat!(env!("OUT_DIR"), "/names.txt"));
#[derive(Clone, Copy)]
pub(crate) struct Name {
    pub text: &'static str,
    pub width: i32,
}
const fn space(byte: u8) -> bool {
    matches!(byte, b' ' | b'\r' | b'\t')
}
const fn count_names(text: &str) -> usize {
    let bytes = text.as_bytes();
    let mut count = 0;
    let mut occupied = false;
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'\n' {
            if occupied {
                count += 1;
            }
            occupied = false;
        } else if !space(bytes[i]) {
            occupied = true;
        }
        i += 1;
    }
    if occupied {
        count += 1;
    }
    if count == 0 { 1 } else { count }
}
pub(crate) const NAME_COUNT: usize = count_names(NAMES_SOURCE);
const fn names() -> [Name; NAME_COUNT] {
    let mut output = [Name {
        text: "Displaitor",
        width: 100,
    }; NAME_COUNT];
    let bytes = NAMES_SOURCE.as_bytes();
    let mut start = 0;
    let mut index = 0;
    while start < bytes.len() {
        let mut end = start;
        while end < bytes.len() && bytes[end] != b'\n' {
            end += 1;
        }
        let next = end + 1;
        while start < end && space(bytes[start]) {
            start += 1;
        }
        while end > start && space(bytes[end - 1]) {
            end -= 1;
        }
        if end > start {
            let text = NAMES_SOURCE.split_at(end).0.split_at(start).1;
            let mut chars = 0;
            let mut p = start;
            while p < end {
                if bytes[p] & 0xc0 != 0x80 {
                    chars += 1;
                }
                p += 1;
            }
            output[index] = Name {
                text,
                width: chars * 10,
            };
            index += 1;
        }
        start = next;
    }
    output
}
pub(crate) static NAMES: [Name; NAME_COUNT] = names();

pub(crate) const SPLASH: [&[u8]; 2] = [
    include_bytes!("../assets/MicroRascon.qoi"),
    include_bytes!("../assets/MicroRascon_Text.qoi"),
];
pub(crate) const NYAN: [&[u8]; 12] = [
    include_bytes!("../assets/nyan/01.qoi"),
    include_bytes!("../assets/nyan/02.qoi"),
    include_bytes!("../assets/nyan/03.qoi"),
    include_bytes!("../assets/nyan/04.qoi"),
    include_bytes!("../assets/nyan/05.qoi"),
    include_bytes!("../assets/nyan/06.qoi"),
    include_bytes!("../assets/nyan/07.qoi"),
    include_bytes!("../assets/nyan/08.qoi"),
    include_bytes!("../assets/nyan/09.qoi"),
    include_bytes!("../assets/nyan/10.qoi"),
    include_bytes!("../assets/nyan/11.qoi"),
    include_bytes!("../assets/nyan/12.qoi"),
];
pub(crate) const HYPER: [&[u8]; 14] = [
    include_bytes!("../assets/hyperspace/0001.qoi"),
    include_bytes!("../assets/hyperspace/0002.qoi"),
    include_bytes!("../assets/hyperspace/0003.qoi"),
    include_bytes!("../assets/hyperspace/0004.qoi"),
    include_bytes!("../assets/hyperspace/0005.qoi"),
    include_bytes!("../assets/hyperspace/0006.qoi"),
    include_bytes!("../assets/hyperspace/0007.qoi"),
    include_bytes!("../assets/hyperspace/0008.qoi"),
    include_bytes!("../assets/hyperspace/0009.qoi"),
    include_bytes!("../assets/hyperspace/0010.qoi"),
    include_bytes!("../assets/hyperspace/0011.qoi"),
    include_bytes!("../assets/hyperspace/0012.qoi"),
    include_bytes!("../assets/hyperspace/0013.qoi"),
    include_bytes!("../assets/hyperspace/0014.qoi"),
];
pub(crate) const FIRE: [&[u8]; 4] = [
    include_bytes!("../assets/fire2/0001.qoi"),
    include_bytes!("../assets/fire2/0002.qoi"),
    include_bytes!("../assets/fire2/0003.qoi"),
    include_bytes!("../assets/fire2/0004.qoi"),
];

pub(crate) fn frames(app: Option<AppId>) -> &'static [&'static [u8]] {
    match app {
        Some(AppId::Nyan) => &NYAN,
        Some(AppId::Hyper) => &HYPER,
        Some(AppId::Fire) => &FIRE,
        _ => &SPLASH,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn compiled_name_index_matches_source_and_unicode_widths() {
        let names = NAMES_SOURCE
            .lines()
            .map(str::trim)
            .filter(|s| !s.is_empty());
        assert_eq!(NAMES.len(), names.clone().count());
        for (indexed, text) in NAMES.iter().zip(names) {
            assert_eq!(indexed.text, text);
            assert_eq!(indexed.width, text.chars().count() as i32 * 10);
        }
    }
}
