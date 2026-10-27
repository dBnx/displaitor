//! Allocation-free navigation over a statically defined menu tree.
//!
//! Menu IDs are direct indexes into the validated menu array. Construction does
//! the graph checks once; navigation thereafter uses a fixed cursor array and
//! constant-time lookups, regardless of menu depth.

use crate::AppId;

/// Direct index of one menu in the static menu array.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct MenuId(usize);

impl MenuId {
    pub const fn new(index: usize) -> Self {
        Self(index)
    }

    pub const fn index(self) -> usize {
        self.0
    }
}

/// Result of activating a menu entry.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Action {
    Menu(MenuId),
    App(AppId),
}

/// One labeled entry in a menu.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Entry<'a> {
    pub label: &'a str,
    pub action: Action,
}

impl<'a> Entry<'a> {
    pub const fn new(label: &'a str, action: Action) -> Self {
        Self { label, action }
    }
}

/// A menu and its direct parent in the static graph.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Menu<'a> {
    pub title: &'a str,
    pub parent: Option<MenuId>,
    pub entries: &'a [Entry<'a>],
}

impl<'a> Menu<'a> {
    pub const fn new(title: &'a str, parent: Option<MenuId>, entries: &'a [Entry<'a>]) -> Self {
        Self {
            title,
            parent,
            entries,
        }
    }
}

/// Direction for moving the current menu cursor.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Direction {
    Up,
    Down,
}

/// Invalid static menu graphs are rejected before navigation begins.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum NavigationError {
    EmptyGraph,
    InvalidRoot,
    RootHasParent,
    EmptyMenu(MenuId),
    InvalidParent(MenuId),
    MissingParent(MenuId),
    WrongParent { menu: MenuId, declared: MenuId },
    DuplicateChild(MenuId),
    UnreferencedMenu(MenuId),
    Cycle(MenuId),
}

/// Navigation state for a static, validated menu tree.
///
/// The cursor for every menu is retained in `[usize; N]`, so returning to a
/// parent restores its prior selection without a navigation stack. `current`
/// and every menu entry are direct indexes; no traversal occurs per update.
#[derive(Clone, Copy)]
pub struct Navigation<'a, const N: usize> {
    menus: &'a [Menu<'a>; N],
    root: MenuId,
    current: MenuId,
    cursors: [usize; N],
}

impl<'a, const N: usize> Navigation<'a, N> {
    /// Validate the static tree once and create its fixed-size runtime state.
    pub fn new(menus: &'a [Menu<'a>; N], root: MenuId) -> Result<Self, NavigationError> {
        if N == 0 {
            return Err(NavigationError::EmptyGraph);
        }
        if root.0 >= N {
            return Err(NavigationError::InvalidRoot);
        }
        if menus[root.0].parent.is_some() {
            return Err(NavigationError::RootHasParent);
        }

        let mut inbound = [0usize; N];
        for (parent_index, menu) in menus.iter().enumerate() {
            if menu.entries.is_empty() {
                return Err(NavigationError::EmptyMenu(MenuId(parent_index)));
            }
            for entry in menu.entries {
                if let Action::Menu(child) = entry.action {
                    if child.0 >= N {
                        return Err(NavigationError::InvalidParent(child));
                    }
                    if child == root {
                        return Err(NavigationError::Cycle(root));
                    }
                    if inbound[child.0] != 0 {
                        return Err(NavigationError::DuplicateChild(child));
                    }
                    inbound[child.0] = 1;
                    match menus[child.0].parent {
                        Some(declared) if declared == MenuId(parent_index) => {}
                        Some(declared) => {
                            return Err(NavigationError::WrongParent {
                                menu: child,
                                declared,
                            });
                        }
                        None => return Err(NavigationError::MissingParent(child)),
                    }
                }
            }
        }

        for (index, menu) in menus.iter().enumerate() {
            let id = MenuId(index);
            if id == root {
                if inbound[index] != 0 {
                    return Err(NavigationError::Cycle(id));
                }
            } else {
                let parent = menu.parent.ok_or(NavigationError::MissingParent(id))?;
                if parent.0 >= N {
                    return Err(NavigationError::InvalidParent(parent));
                }
                if inbound[index] == 0 {
                    return Err(NavigationError::UnreferencedMenu(id));
                }
            }
        }

        // A connected graph with one inbound edge per non-root node is a tree.
        // Walk each parent chain at construction to reject any disconnected
        // cycle explicitly, with work bounded by the static menu count.
        for start in 0..N {
            let mut cursor = MenuId(start);
            let mut steps = 0;
            while cursor != root {
                let Some(parent) = menus[cursor.0].parent else {
                    return Err(NavigationError::UnreferencedMenu(cursor));
                };
                cursor = parent;
                steps += 1;
                if steps >= N {
                    return Err(NavigationError::Cycle(MenuId(start)));
                }
            }
        }

        Ok(Self {
            menus,
            root,
            current: root,
            cursors: [0; N],
        })
    }

    pub const fn menu_id(&self) -> MenuId {
        self.current
    }

    /// Current menu record, including its title and direct parent.
    pub const fn current_menu(&self) -> &'a Menu<'a> {
        &self.menus[self.current.0]
    }

    pub const fn root_id(&self) -> MenuId {
        self.root
    }

    pub const fn selected_index(&self) -> usize {
        self.cursors[self.current.0]
    }

    pub fn selected_entry(&self) -> &'a Entry<'a> {
        &self.menus[self.current.0].entries[self.cursors[self.current.0]]
    }

    /// Move one entry with wraparound. Returns whether the cursor changed.
    pub fn move_selection(&mut self, direction: Direction) -> bool {
        let entries = self.menus[self.current.0].entries;
        let cursor = &mut self.cursors[self.current.0];
        let before = *cursor;
        *cursor = match direction {
            Direction::Down if *cursor + 1 == entries.len() => 0,
            Direction::Down => *cursor + 1,
            Direction::Up if *cursor == 0 => entries.len() - 1,
            Direction::Up => *cursor - 1,
        };
        before != *cursor
    }

    /// Activate the selected entry, entering a child menu in constant time.
    pub fn activate(&mut self) -> Action {
        let action = self.selected_entry().action;
        if let Action::Menu(child) = action {
            self.current = child;
        }
        action
    }

    /// Return to the direct parent, preserving all menu cursors.
    pub fn back(&mut self) -> bool {
        if let Some(parent) = self.menus[self.current.0].parent {
            self.current = parent;
            true
        } else {
            false
        }
    }

    /// First displayed entry in the fixed three-row viewport.
    pub fn visible_start(&self) -> usize {
        self.selected_index().saturating_sub(2)
    }

    /// Number of rows to draw, at most three.
    pub fn visible_len(&self) -> usize {
        (self.menus[self.current.0].entries.len() - self.visible_start()).min(3)
    }

    /// Fetch one row from the fixed three-row viewport.
    pub fn visible_entry(&self, row: usize) -> Option<&'a Entry<'a>> {
        if row >= self.visible_len() {
            return None;
        }
        self.menus[self.current.0]
            .entries
            .get(self.visible_start() + row)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const ROOT_ENTRIES: [Entry<'static>; 2] = [
        Entry::new("sub", Action::Menu(MenuId::new(1))),
        Entry::new("pong", Action::App(AppId::Pong)),
    ];
    const CHILD_ENTRIES: [Entry<'static>; 4] = [
        Entry::new("one", Action::App(AppId::Nyan)),
        Entry::new("two", Action::App(AppId::Hyper)),
        Entry::new("three", Action::App(AppId::Fire)),
        Entry::new("four", Action::App(AppId::Snake)),
    ];
    const MENUS: [Menu<'static>; 2] = [
        Menu::new("root", None, &ROOT_ENTRIES),
        Menu::new("child", Some(MenuId::new(0)), &CHILD_ENTRIES),
    ];
    const CYCLE_ROOT_ENTRIES: [Entry<'static>; 1] =
        [Entry::new("child", Action::Menu(MenuId::new(1)))];
    const CYCLE_CHILD_ENTRIES: [Entry<'static>; 1] =
        [Entry::new("root", Action::Menu(MenuId::new(0)))];
    const CYCLE: [Menu<'static>; 2] = [
        Menu::new("root", None, &CYCLE_ROOT_ENTRIES),
        Menu::new("child", Some(MenuId::new(0)), &CYCLE_CHILD_ENTRIES),
    ];
    const ROOT_ONLY_ENTRIES: [Entry<'static>; 1] = [Entry::new("app", Action::App(AppId::Pong))];
    const SECOND_ROOT_ENTRIES: [Entry<'static>; 1] = [Entry::new("app", Action::App(AppId::Nyan))];
    const WRONG_PARENT: [Menu<'static>; 3] = [
        Menu::new("root", None, &ROOT_ENTRIES),
        Menu::new("child", Some(MenuId::new(2)), &CHILD_ENTRIES),
        Menu::new("other", Some(MenuId::new(0)), &SECOND_ROOT_ENTRIES),
    ];
    const DISCONNECTED_CYCLE_FIRST: [Entry<'static>; 1] =
        [Entry::new("next", Action::Menu(MenuId::new(2)))];
    const DISCONNECTED_CYCLE_SECOND: [Entry<'static>; 1] =
        [Entry::new("next", Action::Menu(MenuId::new(1)))];
    const DISCONNECTED_CYCLE: [Menu<'static>; 3] = [
        Menu::new("root", None, &ROOT_ONLY_ENTRIES),
        Menu::new("first", Some(MenuId::new(2)), &DISCONNECTED_CYCLE_FIRST),
        Menu::new("second", Some(MenuId::new(1)), &DISCONNECTED_CYCLE_SECOND),
    ];
    const DUPLICATE_CHILD_ENTRIES: [Entry<'static>; 2] = [
        Entry::new("child one", Action::Menu(MenuId::new(1))),
        Entry::new("child two", Action::Menu(MenuId::new(1))),
    ];
    const DUPLICATE_CHILD: [Menu<'static>; 2] = [
        Menu::new("root", None, &DUPLICATE_CHILD_ENTRIES),
        Menu::new("child", Some(MenuId::new(0)), &CHILD_ENTRIES),
    ];
    const INVALID_CHILD_ENTRIES: [Entry<'static>; 1] =
        [Entry::new("missing", Action::Menu(MenuId::new(2)))];
    const INVALID_CHILD: [Menu<'static>; 1] = [Menu::new("root", None, &INVALID_CHILD_ENTRIES)];
    const UNREFERENCED_CHILD: [Menu<'static>; 2] = [
        Menu::new("root", None, &ROOT_ONLY_ENTRIES),
        Menu::new("orphan", Some(MenuId::new(0)), &CHILD_ENTRIES),
    ];
    const EMPTY_ENTRIES: [Entry<'static>; 0] = [];
    const EMPTY_MENU: [Menu<'static>; 1] = [Menu::new("empty", None, &EMPTY_ENTRIES)];
    const ROOT_WITH_PARENT: [Menu<'static>; 1] =
        [Menu::new("root", Some(MenuId::new(0)), &SINGLE_ENTRIES)];
    const SINGLE_ENTRIES: [Entry<'static>; 1] = [Entry::new("app", Action::App(AppId::Pong))];
    const SINGLE_MENU: [Menu<'static>; 1] = [Menu::new("single", None, &SINGLE_ENTRIES)];
    const NONZERO_ROOT_ENTRIES: [Entry<'static>; 1] =
        [Entry::new("child", Action::Menu(MenuId::new(0)))];
    const LEAF_ENTRIES: [Entry<'static>; 1] = [Entry::new("app", Action::App(AppId::Pong))];
    const NONZERO_ROOT: [Menu<'static>; 2] = [
        Menu::new("leaf", Some(MenuId::new(1)), &LEAF_ENTRIES),
        Menu::new("root", None, &NONZERO_ROOT_ENTRIES),
    ];

    #[test]
    fn cursor_wraps_and_viewport_stays_at_three_rows() {
        let mut nav = Navigation::new(&MENUS, MenuId::new(0)).unwrap();
        assert_eq!(nav.visible_len(), 2);
        assert!(nav.move_selection(Direction::Up));
        assert_eq!(nav.selected_index(), 1);
        assert!(nav.move_selection(Direction::Down));
        assert_eq!(nav.selected_index(), 0);

        assert_eq!(nav.activate(), Action::Menu(MenuId::new(1)));
        assert_eq!(nav.visible_len(), 3);
        assert_eq!(nav.visible_entry(2).unwrap().label, "three");
        assert_eq!(nav.visible_entry(3), None);
        nav.move_selection(Direction::Down);
        nav.move_selection(Direction::Down);
        nav.move_selection(Direction::Down);
        assert_eq!(nav.visible_start(), 1);
        assert_eq!(nav.visible_len(), 3);
    }

    #[test]
    fn back_is_constant_parent_lookup_and_preserves_parent_cursor() {
        let mut nav = Navigation::new(&MENUS, MenuId::new(0)).unwrap();
        nav.move_selection(Direction::Down);
        assert_eq!(nav.activate(), Action::App(AppId::Pong));
        nav.move_selection(Direction::Up);
        assert_eq!(nav.activate(), Action::Menu(MenuId::new(1)));
        assert!(nav.back());
        assert_eq!(nav.menu_id(), MenuId::new(0));
        assert_eq!(nav.selected_index(), 0);
        assert!(!nav.back());
    }

    #[test]
    fn supports_single_menu_and_nonzero_root() {
        let mut single = Navigation::new(&SINGLE_MENU, MenuId::new(0)).unwrap();
        assert!(!single.move_selection(Direction::Down));
        assert!(!single.move_selection(Direction::Up));
        assert_eq!(single.selected_index(), 0);

        let mut nav = Navigation::new(&NONZERO_ROOT, MenuId::new(1)).unwrap();
        assert_eq!(nav.menu_id(), MenuId::new(1));
        assert_eq!(nav.activate(), Action::Menu(MenuId::new(0)));
        assert!(nav.back());
        assert_eq!(nav.menu_id(), MenuId::new(1));
    }

    #[test]
    fn rejects_invalid_graph_references_and_empty_menus() {
        const BAD_PARENT: [Menu<'static>; 2] = [
            Menu::new("root", None, &ROOT_ENTRIES),
            Menu::new("child", None, &CHILD_ENTRIES),
        ];
        assert_eq!(
            Navigation::new(&BAD_PARENT, MenuId::new(0)).err(),
            Some(NavigationError::MissingParent(MenuId::new(1)))
        );
        assert_eq!(
            Navigation::new(&CYCLE, MenuId::new(0)).err(),
            Some(NavigationError::Cycle(MenuId::new(0)))
        );
        assert_eq!(
            Navigation::new(&EMPTY_MENU, MenuId::new(0)).err(),
            Some(NavigationError::EmptyMenu(MenuId::new(0)))
        );
        assert_eq!(
            Navigation::new(&ROOT_WITH_PARENT, MenuId::new(0)).err(),
            Some(NavigationError::RootHasParent)
        );
        assert_eq!(
            Navigation::new(&MENUS, MenuId::new(2)).err(),
            Some(NavigationError::InvalidRoot)
        );
        assert_eq!(
            Navigation::new(&[], MenuId::new(0)).err(),
            Some(NavigationError::EmptyGraph)
        );
        assert_eq!(
            Navigation::new(&WRONG_PARENT, MenuId::new(0)).err(),
            Some(NavigationError::WrongParent {
                menu: MenuId::new(1),
                declared: MenuId::new(2),
            })
        );
        assert_eq!(
            Navigation::new(&DISCONNECTED_CYCLE, MenuId::new(0)).err(),
            Some(NavigationError::Cycle(MenuId::new(1)))
        );
        assert_eq!(
            Navigation::new(&DUPLICATE_CHILD, MenuId::new(0)).err(),
            Some(NavigationError::DuplicateChild(MenuId::new(1)))
        );
        assert_eq!(
            Navigation::new(&INVALID_CHILD, MenuId::new(0)).err(),
            Some(NavigationError::InvalidParent(MenuId::new(2)))
        );
        assert_eq!(
            Navigation::new(&UNREFERENCED_CHILD, MenuId::new(0)).err(),
            Some(NavigationError::UnreferencedMenu(MenuId::new(1)))
        );
    }
}
