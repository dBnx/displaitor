use alloc::boxed::Box;
use embedded_graphics::prelude::*;

use crate::{
    apps::{Animation, Dummy, Image, Menu, ScrollingText, SplashScreen},
    games::{GameBoy, Pong, Snake, SpaceInvader},
    trait_app::{Color, RenderStatus, UpdateResult},
    App, Controls,
};

pub const MAX_MENU_ENTRIES: usize = 10;

pub enum AppEnum<D, C>
where
    D: DrawTarget<Color = C>,
    C: Color,
{
    Animation(Animation<D, C, 14>),
    Dummy(Dummy<D, C>),
    Image(Image<D, C>),
    Menu(Box<Menu<MAX_MENU_ENTRIES, D, C>>),
    ScrollingText(ScrollingText<D, C, 109>),
    SplashScreen(SplashScreen<D, C>),
    GameBoy(GameBoy),
    Pong(Pong<D, C>),
    Snake(Snake<64, 32, 32, D, C>),
    SpaceInvader(SpaceInvader),
}

impl<D, C> AppEnum<D, C>
where
    D: DrawTarget<Color = C>,
    C: Color,
{
    pub fn as_menu(&self) -> Option<&Menu<MAX_MENU_ENTRIES, D, C>> {
        match self {
            AppEnum::Menu(menu) => Some(menu.as_ref()),
            _ => None,
        }
    }

    pub fn as_menu_mut(&mut self) -> Option<&mut Menu<MAX_MENU_ENTRIES, D, C>> {
        match self {
            AppEnum::Menu(menu) => Some(menu.as_mut()),
            _ => None,
        }
    }
}

impl<D, C> App for AppEnum<D, C>
where
    D: DrawTarget<Color = C>,
    C: Color,
{
    type Target = D;
    type Color = C;

    fn reset_state(&mut self) {
        match self {
            AppEnum::Animation(app) => app.reset_state(),
            AppEnum::Dummy(app) => app.reset_state(),
            AppEnum::Image(app) => app.reset_state(),
            AppEnum::Menu(app) => app.reset_state(),
            AppEnum::ScrollingText(app) => app.reset_state(),
            AppEnum::SplashScreen(app) => app.reset_state(),
            AppEnum::GameBoy(_) => {}
            AppEnum::Pong(app) => app.reset_state(),
            AppEnum::Snake(app) => app.reset_state(),
            AppEnum::SpaceInvader(_) => {}
        }
    }

    fn update(&mut self, dt_us: i64, t_us: i64, controls: &Controls) -> UpdateResult {
        match self {
            AppEnum::Animation(app) => app.update(dt_us, t_us, controls),
            AppEnum::Dummy(app) => app.update(dt_us, t_us, controls),
            AppEnum::Image(app) => app.update(dt_us, t_us, controls),
            AppEnum::Menu(app) => app.as_mut().update(dt_us, t_us, controls),
            AppEnum::ScrollingText(app) => app.update(dt_us, t_us, controls),
            AppEnum::SplashScreen(app) => app.update(dt_us, t_us, controls),
            AppEnum::GameBoy(_) => RenderStatus::NoVisibleChange.into(),
            AppEnum::Pong(app) => app.update(dt_us, t_us, controls),
            AppEnum::Snake(app) => app.update(dt_us, t_us, controls),
            AppEnum::SpaceInvader(_) => RenderStatus::NoVisibleChange.into(),
        }
    }

    fn render(&self, target: &mut Self::Target) {
        match self {
            AppEnum::Animation(app) => app.render(target),
            AppEnum::Dummy(app) => app.render(target),
            AppEnum::Image(app) => app.render(target),
            AppEnum::Menu(app) => app.render(target),
            AppEnum::ScrollingText(app) => app.render(target),
            AppEnum::SplashScreen(app) => app.render(target),
            AppEnum::GameBoy(_) => {}
            AppEnum::Pong(app) => app.render(target),
            AppEnum::Snake(app) => app.render(target),
            AppEnum::SpaceInvader(_) => {}
        }
    }

    fn teardown(&mut self) {
        match self {
            AppEnum::Animation(app) => app.teardown(),
            AppEnum::Dummy(app) => app.teardown(),
            AppEnum::Image(app) => app.teardown(),
            AppEnum::Menu(app) => app.teardown(),
            AppEnum::ScrollingText(app) => app.teardown(),
            AppEnum::SplashScreen(app) => app.teardown(),
            AppEnum::GameBoy(_) => {}
            AppEnum::Pong(app) => app.teardown(),
            AppEnum::Snake(app) => app.teardown(),
            AppEnum::SpaceInvader(_) => {}
        }
    }

    fn close_request(&self) -> bool {
        match self {
            AppEnum::Animation(app) => app.close_request(),
            AppEnum::Dummy(app) => app.close_request(),
            AppEnum::Image(app) => app.close_request(),
            AppEnum::Menu(app) => app.close_request(),
            AppEnum::ScrollingText(app) => app.close_request(),
            AppEnum::SplashScreen(app) => app.close_request(),
            AppEnum::GameBoy(_) => false,
            AppEnum::Pong(app) => app.close_request(),
            AppEnum::Snake(app) => app.close_request(),
            AppEnum::SpaceInvader(_) => false,
        }
    }
}

impl<D, C> From<Animation<D, C, 14>> for AppEnum<D, C>
where
    D: DrawTarget<Color = C>,
    C: Color,
{
    fn from(app: Animation<D, C, 14>) -> Self {
        AppEnum::Animation(app)
    }
}

impl<D, C> From<Dummy<D, C>> for AppEnum<D, C>
where
    D: DrawTarget<Color = C>,
    C: Color,
{
    fn from(app: Dummy<D, C>) -> Self {
        AppEnum::Dummy(app)
    }
}

impl<D, C> From<Image<D, C>> for AppEnum<D, C>
where
    D: DrawTarget<Color = C>,
    C: Color,
{
    fn from(app: Image<D, C>) -> Self {
        AppEnum::Image(app)
    }
}

impl<D, C> From<Menu<MAX_MENU_ENTRIES, D, C>> for AppEnum<D, C>
where
    D: DrawTarget<Color = C>,
    C: Color,
{
    fn from(app: Menu<MAX_MENU_ENTRIES, D, C>) -> Self {
        AppEnum::Menu(Box::new(app))
    }
}

impl<D, C> From<ScrollingText<D, C, 109>> for AppEnum<D, C>
where
    D: DrawTarget<Color = C>,
    C: Color,
{
    fn from(app: ScrollingText<D, C, 109>) -> Self {
        AppEnum::ScrollingText(app)
    }
}

impl<D, C> From<SplashScreen<D, C>> for AppEnum<D, C>
where
    D: DrawTarget<Color = C>,
    C: Color,
{
    fn from(app: SplashScreen<D, C>) -> Self {
        AppEnum::SplashScreen(app)
    }
}

impl<D, C> From<GameBoy> for AppEnum<D, C>
where
    D: DrawTarget<Color = C>,
    C: Color,
{
    fn from(app: GameBoy) -> Self {
        AppEnum::GameBoy(app)
    }
}

impl<D, C> From<Pong<D, C>> for AppEnum<D, C>
where
    D: DrawTarget<Color = C>,
    C: Color,
{
    fn from(app: Pong<D, C>) -> Self {
        AppEnum::Pong(app)
    }
}

impl<D, C> From<Snake<64, 32, 32, D, C>> for AppEnum<D, C>
where
    D: DrawTarget<Color = C>,
    C: Color,
{
    fn from(app: Snake<64, 32, 32, D, C>) -> Self {
        AppEnum::Snake(app)
    }
}

impl<D, C> From<SpaceInvader> for AppEnum<D, C>
where
    D: DrawTarget<Color = C>,
    C: Color,
{
    fn from(app: SpaceInvader) -> Self {
        AppEnum::SpaceInvader(app)
    }
}

