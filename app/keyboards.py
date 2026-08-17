"""Native VK keyboards для mini-MVP."""

from vkbottle import Keyboard, KeyboardButtonColor, Text


MAIN_KEYBOARD = (
    Keyboard(one_time=False)
    .add(Text("Написать пост"), color=KeyboardButtonColor.PRIMARY)
    .add(Text("Продающий текст"), color=KeyboardButtonColor.PRIMARY)
    .row()
    .add(Text("Ответить клиенту"), color=KeyboardButtonColor.PRIMARY)
    .add(Text("Идеи контента"), color=KeyboardButtonColor.PRIMARY)
    .row()
    .add(Text("Ещё"), color=KeyboardButtonColor.SECONDARY)
    .get_json()
)

MORE_KEYBOARD = (
    Keyboard(one_time=False)
    .add(Text("Переписать текст"), color=KeyboardButtonColor.PRIMARY)
    .add(Text("Профиль бренда"), color=KeyboardButtonColor.PRIMARY)
    .row()
    .add(Text("Помощь"), color=KeyboardButtonColor.SECONDARY)
    .add(Text("Меню"), color=KeyboardButtonColor.SECONDARY)
    .get_json()
)

INPUT_KEYBOARD = (
    Keyboard(one_time=False)
    .add(Text("Отмена"), color=KeyboardButtonColor.SECONDARY)
    .add(Text("Меню"), color=KeyboardButtonColor.SECONDARY)
    .get_json()
)

RESULT_KEYBOARD = (
    Keyboard(one_time=False)
    .add(Text("Подходит"), color=KeyboardButtonColor.POSITIVE)
    .add(Text("Ещё вариант"), color=KeyboardButtonColor.PRIMARY)
    .row()
    .add(Text("Изменить вручную"), color=KeyboardButtonColor.SECONDARY)
    .add(Text("Меню"), color=KeyboardButtonColor.SECONDARY)
    .get_json()
)
