use crate::{
    AudioId, Controls, content, cozy,
    games::{Pong, Snake},
    navigation::{Action, Direction, Menu, MenuId, Navigation, NavigationError},
};
use core::time::Duration;
use embedded_graphics::pixelcolor::Rgb565;

// Scheduling and advancement use the same periods so deadlines cannot drift
// from the application's tick rate when a period changes.
const NAMES_PERIOD_US: u64 = 30_000;
const ANIMATION_PERIOD_US: u64 = 50_000;
const PONG_PERIOD_US: u64 = 20_000;
const SNAKE_PERIOD_US: u64 = 60_000;

// One declaration supplies dense IDs, the complete list and diagnostic storage sizes.
macro_rules! application_ids {
    ($($app:ident),+ $(,)?) => {
        /// Concrete applications are dispatched directly, independently of menu depth.
        #[derive(Clone, Copy, Debug, PartialEq, Eq)]
        #[repr(u8)]
        pub enum AppId { $($app),+ }

        impl AppId {
            /// Every application in dense diagnostic-index order.
            pub const ALL: &[Self] = &[$(Self::$app),+];
            /// Storage size generated from the same declaration as the IDs.
            pub const COUNT: usize = Self::ALL.len();
        }
    };
}

application_ids! {
    Names,
    Nyan,
    Hyper,
    Fire,
    Pong,
    Snake,
    Canvas,
    CozyFarm,
    CozyWinter,
    CozyOkami,
    CozyWitcher,
    CozyReef,
    CozyPalico,
    CozyRathalos,
    CozyZinogre,
    CozyPoogie,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Screen {
    Splash,
    Menu(MenuId),
    App(AppId),
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
#[must_use = "Apply redraw and audio requests in the platform adapter"]
pub struct Update {
    pub redraw: bool,
    pub audio: Option<AudioId>,
}

// Inline bounded storage avoids an allocator and dynamic dispatch.
#[allow(clippy::large_enum_variant)]
enum Game {
    None,
    Pong(Pong),
    Snake(Snake),
}

/// Inferred from the catalog, so adding a built-in menu needs no runtime edits.
pub const DEFAULT_MENU_COUNT: usize = content::MENUS.len();

/// A direct application runtime and a separately indexed menu graph.
///
/// Menu depth never enters update/render dispatch. `N` sizes the cursor array,
/// not a stack; idle work and navigation transitions are constant time. The
/// default catalog has four menus; custom static trees use `with_menus`.
pub struct Engine<const N: usize = DEFAULT_MENU_COUNT> {
    pub(crate) canvas: crate::canvas::Canvas,
    pub(crate) screen: Screen,
    pub(crate) navigation: Navigation<'static, N>,
    previous: Controls,
    initial: bool,
    canvas_requested: bool,
    timer_us: u64,
    pub(crate) frame: usize,
    pub(crate) name_index: usize,
    pub(crate) name_next: usize,
    pub(crate) name_offset: i32,
    pub(crate) name_color: Rgb565,
    pub(crate) next_color: Rgb565,
    random: u32,
    game: Game,
    cozy_paused: bool,
    pub(crate) cozy_action_us: Option<u64>,
}

impl Default for Engine<DEFAULT_MENU_COUNT> {
    fn default() -> Self {
        Self::new()
    }
}
impl Engine<DEFAULT_MENU_COUNT> {
    pub fn new() -> Self {
        Self::with_menus(&content::MENUS, content::ROOT).expect("built-in menu catalog is valid")
    }
}

impl<const N: usize> Engine<N> {
    /// Checks the complete menu graph once. No validation or parent walk occurs per frame.
    pub fn with_menus(
        menus: &'static [Menu<'static>; N],
        root: MenuId,
    ) -> Result<Self, NavigationError> {
        Ok(Self {
            canvas: crate::canvas::Canvas::new(),
            screen: Screen::Splash,
            navigation: Navigation::new(menus, root)?,
            previous: Controls::default(),
            initial: true,
            canvas_requested: false,
            timer_us: 0,
            frame: 0,
            name_index: 0,
            name_next: 1 % content::NAME_COUNT,
            name_offset: 0,
            name_color: Rgb565::new(0, 63, 0),
            next_color: Rgb565::new(0, 63, 31),
            random: 0xdead_beef,
            game: Game::None,
            cozy_paused: false,
            cozy_action_us: None,
        })
    }
    pub const fn screen(&self) -> Screen {
        self.screen
    }
    /// Time until autonomous screen work, measured after the last update.
    /// Static screens need only input or remote-command notifications.
    pub fn next_update_after(&self) -> Option<Duration> {
        let period_us: u64 = match self.screen {
            Screen::Splash => {
                if self.timer_us < 2_000_000 {
                    2_000_000
                } else {
                    4_000_000
                }
            }
            Screen::Menu(_) | Screen::App(AppId::Canvas) => return None,
            Screen::App(AppId::Names) => NAMES_PERIOD_US,
            Screen::App(AppId::Nyan | AppId::Hyper) => ANIMATION_PERIOD_US,
            Screen::App(
                id @ (AppId::CozyFarm
                | AppId::CozyWinter
                | AppId::CozyOkami
                | AppId::CozyWitcher
                | AppId::CozyReef
                | AppId::Fire
                | AppId::CozyPalico
                | AppId::CozyRathalos
                | AppId::CozyZinogre
                | AppId::CozyPoogie),
            ) => {
                let ambient = (!self.cozy_paused)
                    .then(|| cozy::clip(id).period_us().saturating_sub(self.timer_us));
                let action = self
                    .cozy_action_us
                    .map(|us| cozy::ACTION_PERIOD_US - us % cozy::ACTION_PERIOD_US);
                return ambient
                    .into_iter()
                    .chain(action)
                    .min()
                    .map(Duration::from_micros);
            }
            Screen::App(AppId::Pong) => PONG_PERIOD_US,
            Screen::App(AppId::Snake) if self.game_over() => return None,
            Screen::App(AppId::Snake) => SNAKE_PERIOD_US,
        };
        let remaining = period_us.saturating_sub(self.timer_us);
        let remaining = self.cozy_action_us.map_or(remaining, |us| {
            remaining.min(cozy::ACTION_PERIOD_US - us % cozy::ACTION_PERIOD_US)
        });
        Some(Duration::from_micros(remaining))
    }
    pub fn canvas_mut(&mut self) -> &mut crate::canvas::Canvas {
        &mut self.canvas
    }
    pub fn canvas(&self) -> &crate::canvas::Canvas {
        &self.canvas
    }
    /// Immediate local platform launch (e.g. simulator CLI).
    pub fn open_canvas(&mut self) -> Update {
        self.open_app(AppId::Canvas)
    }
    /// Immediate local platform launch, with the same entry/reset policy as a menu.
    pub fn open_app(&mut self, app: AppId) -> Update {
        let update = self.enter_app(app);
        self.canvas
            .record_buttons(Duration::ZERO, self.previous, app == AppId::Canvas);
        update
    }
    /// Queue explicit remote activation for the normal update/audio/render path.
    /// Repeated requests while already in Canvas are harmless. Local B wins.
    pub fn request_canvas(&mut self) {
        self.canvas_requested = true;
    }
    pub const fn selected_entry(&self) -> usize {
        self.navigation.selected_index()
    }
    pub const fn navigation(&self) -> &Navigation<'static, N> {
        &self.navigation
    }
    pub fn game_over(&self) -> bool {
        matches!(&self.game, Game::Snake(snake) if snake.over)
    }

    pub fn update(&mut self, elapsed: Duration, controls: Controls) -> Update {
        self.update_inner(elapsed, controls, true)
    }

    /// Replay local input before consuming remote navigation at the batch cutoff.
    /// A local Back cancels a pending Show, preserving its normal priority.
    pub fn update_local(&mut self, elapsed: Duration, controls: Controls) -> Update {
        self.update_inner(elapsed, controls, false)
    }

    fn update_inner(&mut self, elapsed: Duration, controls: Controls, remote: bool) -> Update {
        let update = self.update_screen(elapsed, controls, remote);
        self.canvas
            .record_buttons(elapsed, controls, self.screen == Screen::App(AppId::Canvas));
        update
    }

    fn update_screen(&mut self, elapsed: Duration, controls: Controls, remote: bool) -> Update {
        let edges = controls.rising(self.previous);
        self.previous = controls;
        let canvas_requested = remote && core::mem::take(&mut self.canvas_requested);
        let canvas_audio = if remote {
            self.canvas.take_audio_request()
        } else {
            None
        };
        let mut update = Update {
            redraw: core::mem::take(&mut self.initial),
            audio: None,
        };
        if edges.buttons_b {
            self.canvas_requested = false;
            let _ = self.canvas.take_audio_request();
            return match self.screen {
                Screen::Splash => self.enter_app(AppId::Names),
                Screen::App(_) => {
                    self.screen = Screen::Menu(self.navigation.menu_id());
                    self.game = Game::None;
                    Update {
                        redraw: true,
                        audio: Some(AudioId::Stop),
                    }
                }
                Screen::Menu(_) => {
                    if self.navigation.back() {
                        self.screen = Screen::Menu(self.navigation.menu_id());
                        update.redraw = true;
                    }
                    update
                }
            };
        }
        if canvas_requested && self.screen != Screen::App(AppId::Canvas) {
            return self.enter_app(AppId::Canvas);
        }
        match self.screen {
            Screen::Splash => {
                self.timer_us = self
                    .timer_us
                    .saturating_add(elapsed.as_micros().min(u128::from(u64::MAX)) as u64);
                if self.timer_us >= 4_000_000 {
                    return self.enter_app(AppId::Names);
                }
                let frame = usize::from(self.timer_us >= 2_000_000);
                update.redraw |= self.frame != frame;
                self.frame = frame;
            }
            Screen::Menu(_) => {
                if edges.dpad_down != edges.dpad_up {
                    update.redraw |= self.navigation.move_selection(if edges.dpad_down {
                        Direction::Down
                    } else {
                        Direction::Up
                    });
                }
                if edges.buttons_a {
                    return match self.navigation.activate() {
                        Action::Menu(id) => {
                            self.screen = Screen::Menu(id);
                            Update {
                                redraw: true,
                                audio: None,
                            }
                        }
                        Action::App(id) => self.enter_app(id),
                    };
                }
            }
            Screen::App(AppId::Canvas) => {
                update.redraw |= self.canvas.take_dirty();
                update.audio = canvas_audio;
            }
            Screen::App(AppId::Names) => {
                let steps = self.ticks(elapsed.min(Duration::from_millis(250)), NAMES_PERIOD_US);
                for _ in 0..steps {
                    self.name_offset += 1;
                    let width = content::NAMES[self.name_index].width;
                    if self.name_offset >= width {
                        self.name_offset -= width;
                        self.name_index = self.name_next;
                        self.name_color = self.next_color;
                        self.name_next = self.random() as usize % content::NAME_COUNT;
                        let rgb = self.random();
                        self.next_color = Rgb565::new(
                            ((rgb >> 16) as u8 & 31).max(8),
                            ((rgb >> 8) as u8 & 63).max(16),
                            (rgb as u8 & 31).max(8),
                        );
                    }
                }
                update.redraw |= steps != 0;
            }
            Screen::App(id @ (AppId::Nyan | AppId::Hyper)) => {
                let steps = self.ticks(elapsed, ANIMATION_PERIOD_US);
                update.redraw |= self.advance_movie_action(elapsed, edges.buttons_a);
                let count = content::frames(Some(id)).len();
                let next = (self.frame + (steps % count as u128) as usize) % count;
                update.redraw |= next != self.frame;
                self.frame = next;
            }
            Screen::App(
                id @ (AppId::CozyFarm
                | AppId::CozyWinter
                | AppId::CozyOkami
                | AppId::CozyWitcher
                | AppId::CozyReef
                | AppId::Fire
                | AppId::CozyPalico
                | AppId::CozyRathalos
                | AppId::CozyZinogre
                | AppId::CozyPoogie),
            ) => {
                if edges.dpad_left != edges.dpad_right {
                    let paused = self.cozy_paused;
                    let next = cozy::adjacent(id, edges.dpad_right);
                    let effects = self.enter_app(next);
                    self.cozy_paused = paused;
                    return effects;
                }
                if !self.cozy_paused {
                    let clip = cozy::clip(id);
                    let steps = self.ticks(elapsed, clip.period_us());
                    let next = (self.frame + (steps % clip.len() as u128) as usize) % clip.len();
                    update.redraw |= clip.frame_id(next) != clip.frame_id(self.frame);
                    self.frame = next;
                }
                update.redraw |= self.advance_movie_action(elapsed, edges.buttons_a);
                // Elapsed time belongs to the state before this input edge:
                // pausing includes it; resuming never advances across the pause.
                if edges.dpad_up != edges.dpad_down {
                    self.cozy_paused = edges.dpad_up;
                }
            }
            Screen::App(AppId::Pong) => {
                let steps = self.ticks(elapsed.min(Duration::from_millis(250)), PONG_PERIOD_US);
                if let Game::Pong(pong) = &mut self.game {
                    for _ in 0..steps {
                        update.audio = pong.step(controls).or(update.audio);
                    }
                }
                update.redraw |= steps != 0;
            }
            Screen::App(AppId::Snake) => {
                if edges.buttons_a && self.game_over() {
                    return self.enter_app(AppId::Snake);
                }
                let steps = self.ticks(elapsed.min(Duration::from_millis(250)), SNAKE_PERIOD_US);
                if let Game::Snake(snake) = &mut self.game {
                    snake.steer(controls);
                    for _ in 0..steps {
                        if snake.over {
                            break;
                        }
                        update.audio = snake.step().or(update.audio);
                        update.redraw = true;
                    }
                }
            }
        }
        update
    }
    fn ticks(&mut self, elapsed: Duration, period_us: u64) -> u128 {
        let total = elapsed.as_micros() + u128::from(self.timer_us);
        self.timer_us = (total % u128::from(period_us)) as u64;
        total / u128::from(period_us)
    }
    fn random(&mut self) -> u32 {
        self.random ^= self.random << 13;
        self.random ^= self.random >> 17;
        self.random ^= self.random << 5;
        self.random
    }
    fn advance_movie_action(&mut self, elapsed: Duration, pressed: bool) -> bool {
        let mut redraw = false;
        if let Some(before) = self.cozy_action_us {
            let after = (u128::from(before) + elapsed.as_micros())
                .min(u128::from(cozy::ACTION_DURATION_US)) as u64;
            self.cozy_action_us = (after < cozy::ACTION_DURATION_US).then_some(after);
            redraw = self.cozy_action_us.is_none()
                || before / cozy::ACTION_PERIOD_US != after / cozy::ACTION_PERIOD_US;
        }
        if pressed {
            self.cozy_action_us = Some(0);
            redraw = true;
        }
        redraw
    }

    fn enter_app(&mut self, id: AppId) -> Update {
        self.screen = Screen::App(id);
        self.timer_us = 0;
        self.frame = 0;
        self.cozy_paused = false;
        self.cozy_action_us = None;
        self.name_offset = 0;
        self.name_index = 0;
        self.name_next = 1 % content::NAME_COUNT;
        self.name_color = Rgb565::new(0, 63, 0);
        self.next_color = Rgb565::new(0, 63, 31);
        self.game = match id {
            AppId::Pong => Game::Pong(Pong::new()),
            AppId::Snake => Game::Snake(Snake::new()),
            _ => Game::None,
        };
        Update {
            redraw: true,
            audio: Some(if id == AppId::Nyan {
                AudioId::MusicNyan
            } else {
                AudioId::Stop
            }),
        }
    }
    pub(crate) fn pong(&self) -> Option<&Pong> {
        match &self.game {
            Game::Pong(pong) => Some(pong),
            _ => None,
        }
    }
    pub(crate) fn snake(&self) -> Option<&Snake> {
        match &self.game {
            Game::Snake(snake) => Some(snake),
            _ => None,
        }
    }
}
