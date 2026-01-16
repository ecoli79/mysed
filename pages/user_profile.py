from nicegui import ui
from auth.middleware import get_current_user, require_auth
from auth.ldap_auth import LDAPAuthenticator
from auth.token_storage import token_storage, clear_last_token
from auth.session_manager import session_manager
from app_logging.logger import get_logger
import re
import asyncio

logger = get_logger(__name__)

@require_auth
def content():
    """Создает страницу профиля пользователя"""
    user = get_current_user()
    
    if not user:
        ui.label('Ошибка: пользователь не найден').classes('text-red-500')
        return
    
    with ui.column().classes('w-full max-w-2xl gap-6'):
        # Заголовок
        ui.label('Профиль пользователя').classes('text-2xl font-bold text-gray-800')
        
        # Карточка с информацией о пользователе
        with ui.card().classes('w-full p-6 shadow-lg'):
            with ui.column().classes('w-full gap-4'):
                # Имя и фамилия
                with ui.row().classes('items-center gap-3'):
                    ui.icon('person', size='lg').classes('text-primary')
                    with ui.column().classes('gap-1'):
                        ui.label('Имя и фамилия').classes('text-sm text-gray-600')
                        ui.label(f'{user.first_name} {user.last_name}').classes('text-lg font-semibold text-gray-800')
                
                ui.separator()
                
                # Электронная почта
                with ui.row().classes('items-center gap-3'):
                    ui.icon('email', size='lg').classes('text-primary')
                    with ui.column().classes('gap-1'):
                        ui.label('Адрес электронной почты').classes('text-sm text-gray-600')
                        emailDisplay = user.email if user.email else 'Не указан'
                        ui.label(emailDisplay).classes('text-lg font-semibold text-gray-800')
                
                ui.separator()
                
                # Логин
                with ui.row().classes('items-center gap-3'):
                    ui.icon('badge', size='lg').classes('text-primary')
                    with ui.column().classes('gap-1'):
                        ui.label('Логин').classes('text-sm text-gray-600')
                        ui.label(user.username).classes('text-lg font-semibold text-gray-800')
                
                ui.separator()
                
                # Должность
                with ui.row().classes('items-center gap-3'):
                    ui.icon('work', size='lg').classes('text-primary')
                    with ui.column().classes('gap-1'):
                        ui.label('Должность').classes('text-sm text-gray-600')
                        if user.description:
                            ui.label(user.description).classes('text-lg font-semibold text-gray-800')
                        else:
                            ui.label('Не указана').classes('text-lg font-semibold text-gray-500')
                
                ui.separator()
                
                # Роли (группы)
                with ui.row().classes('items-center gap-3'):
                    ui.icon('group', size='lg').classes('text-primary')
                    with ui.column().classes('gap-1'):
                        ui.label('Роли').classes('text-sm text-gray-600')
                        if user.groups:
                            groupsDisplay = ', '.join(user.groups)
                            ui.label(groupsDisplay).classes('text-lg font-semibold text-gray-800')
                        else:
                            ui.label('Не указаны').classes('text-lg font-semibold text-gray-500')
                
                ui.separator()
                
                # Статус активности
                with ui.row().classes('items-center gap-3'):
                    ui.icon('check_circle' if user.is_active else 'cancel', size='lg').classes(
                        'text-green-600' if user.is_active else 'text-red-600'
                    )
                    with ui.column().classes('gap-1'):
                        ui.label('Статус').classes('text-sm text-gray-600')
                        statusText = 'Активен' if user.is_active else 'Неактивен'
                        ui.label(statusText).classes(
                            'text-lg font-semibold ' + 
                            ('text-green-600' if user.is_active else 'text-red-600')
                        )
        
        # Форма смены пароля
        with ui.card().classes('w-full p-6 shadow-lg'):
            ui.label('Смена пароля').classes('text-xl font-bold text-gray-800 mb-4')
            
            # Поля формы
            currentPasswordInput = ui.input(
                'Текущий пароль',
                password=True,
                password_toggle_button=True
            ).classes('w-full').props('outlined')
            
            newPasswordInput = ui.input(
                'Новый пароль',
                password=True,
                password_toggle_button=True
            ).classes('w-full').props('outlined')
            
            confirmPasswordInput = ui.input(
                'Подтверждение нового пароля',
                password=True,
                password_toggle_button=True
            ).classes('w-full').props('outlined')
            
            # Требования к паролю
            with ui.column().classes('w-full gap-2 mt-2'):
                ui.label('Требования к паролю:').classes('text-sm font-semibold text-gray-700')
                requirementsList = ui.column().classes('gap-1')
                with requirementsList:
                    minLengthReq = ui.label('• Минимум 8 символов').classes('text-xs text-gray-600')
                    hasUpperReq = ui.label('• Хотя бы одна заглавная буква').classes('text-xs text-gray-600')
                    hasLowerReq = ui.label('• Хотя бы одна строчная буква').classes('text-xs text-gray-600')
                    hasDigitReq = ui.label('• Хотя бы одна цифра').classes('text-xs text-gray-600')
                    hasSpecialReq = ui.label('• Хотя бы один специальный символ (@#$%^&*)').classes('text-xs text-gray-600')
            
            # Индикатор силы пароля
            strengthContainer = ui.column().classes('w-full mt-2')
            with strengthContainer:
                strengthLabel = ui.label('').classes('hidden')  # Скрываем label, чтобы не занимал место
                strengthBar = ui.linear_progress(show_value=False).classes('w-full h-2')
            
            # Сообщения об ошибках
            errorLabel = ui.label('').classes('text-sm text-red-600 mt-2')
            successLabel = ui.label('').classes('text-sm text-green-600 mt-2')
            
            # Кнопка смены пароля
            changePasswordButton = ui.button(
                'Изменить пароль',
                icon='lock',
                on_click=lambda: handle_password_change()
            ).classes('mt-4 bg-primary text-white')
            
            def calculate_password_strength(password: str) -> tuple[int, str, str]:
                """
                Вычисляет силу пароля
                Returns: (score 0-100, label, color)
                """
                if not password:
                    return (0, '', 'gray')
                
                score = 0
                checks = {
                    'length': len(password) >= 8,
                    'upper': bool(re.search(r'[A-ZА-Я]', password)),
                    'lower': bool(re.search(r'[a-zа-я]', password)),
                    'digit': bool(re.search(r'\d', password)),
                    'special': bool(re.search(r'[@#$%^&*()_+\-=\[\]{};\':"\\|,.<>\/?!]', password))
                }
                
                # Базовые проверки
                if checks['length']:
                    score += 20
                if checks['upper']:
                    score += 20
                if checks['lower']:
                    score += 20
                if checks['digit']:
                    score += 20
                if checks['special']:
                    score += 20
                
                # Дополнительные бонусы за длину
                if len(password) >= 12:
                    score = min(100, score + 10)
                if len(password) >= 16:
                    score = min(100, score + 10)
                
                if score < 40:
                    return (score, 'Слабый', 'red')
                elif score < 70:
                    return (score, 'Средний', 'orange')
                elif score < 90:
                    return (score, 'Хороший', 'blue')
                else:
                    return (score, 'Отличный', 'green')
            
            def update_password_requirements(password: str):
                """Обновляет визуализацию требований к паролю"""
                checks = {
                    'length': len(password) >= 8,
                    'upper': bool(re.search(r'[A-ZА-Я]', password)),
                    'lower': bool(re.search(r'[a-zа-я]', password)),
                    'digit': bool(re.search(r'\d', password)),
                    'special': bool(re.search(r'[@#$%^&*()_+\-=\[\]{};\':"\\|,.<>\/?!]', password))
                }
                
                minLengthReq.classes('text-xs ' + ('text-green-600' if checks['length'] else 'text-gray-600'))
                hasUpperReq.classes('text-xs ' + ('text-green-600' if checks['upper'] else 'text-gray-600'))
                hasLowerReq.classes('text-xs ' + ('text-green-600' if checks['lower'] else 'text-gray-600'))
                hasDigitReq.classes('text-xs ' + ('text-green-600' if checks['digit'] else 'text-gray-600'))
                hasSpecialReq.classes('text-xs ' + ('text-green-600' if checks['special'] else 'text-gray-600'))
            
            def update_password_strength(password: str):
                """Обновляет индикатор силы пароля"""
                if not password:
                    strengthLabel.text = ''
                    strengthBar.value = 0
                    strengthBar.classes('w-full h-2')
                    return
                
                score, label, color = calculate_password_strength(password)
                strengthLabel.text = ''  # Убираем текст, оставляем только прогресс-бар
                strengthBar.value = score / 100
                
                colorMap = {
                    'red': 'bg-red-500',
                    'orange': 'bg-orange-500',
                    'blue': 'bg-blue-500',
                    'green': 'bg-green-500',
                    'gray': 'bg-gray-300'
                }
                strengthBar.classes(f'w-full h-2 {colorMap.get(color, "bg-gray-300")}')
            
            def check_passwords_match(show_error=True):
                """Проверяет совпадение паролей и обновляет сообщение об ошибке"""
                # Получаем значения напрямую из полей
                newPassword = str(newPasswordInput.value) if newPasswordInput.value else ''
                confirmPassword = str(confirmPasswordInput.value) if confirmPasswordInput.value else ''
                
                # Не показываем ошибку, если одно из полей пустое
                if not newPassword or not confirmPassword:
                    if show_error:
                        errorLabel.text = ''
                    return True
                
                # Проверяем совпадение
                if newPassword != confirmPassword:
                    if show_error:
                        errorLabel.text = 'Пароли не совпадают'
                        errorLabel.classes('text-sm text-red-600 mt-2')
                    return False
                else:
                    if show_error:
                        errorLabel.text = ''
                    return True
            
            # Обработчики событий для полей пароля
            def on_new_password_change(e=None):
                password = str(newPasswordInput.value) if newPasswordInput.value else ''
                update_password_requirements(password)
                update_password_strength(password)
                # Очищаем ошибку при изменении нового пароля, если поле подтверждения пустое
                if not confirmPasswordInput.value:
                    errorLabel.text = ''
            
            def on_confirm_password_blur(e=None):
                """Проверяет совпадение паролей при потере фокуса поля подтверждения"""
                check_passwords_match()
            
            # Обработчики событий
            newPasswordInput.on('update:model-value', on_new_password_change)
            confirmPasswordInput.on('blur', on_confirm_password_blur)
            
            async def handle_password_change():
                """Обработчик смены пароля"""
                # Очищаем предыдущие сообщения
                errorLabel.text = ''
                successLabel.text = ''
                
                # Получаем значения полей (преобразуем в строки для надежности)
                currentPassword = str(currentPasswordInput.value) if currentPasswordInput.value else ''
                newPassword = str(newPasswordInput.value) if newPasswordInput.value else ''
                confirmPassword = str(confirmPasswordInput.value) if confirmPasswordInput.value else ''
                
                # Валидация на клиенте
                if not currentPassword:
                    errorLabel.text = 'Введите текущий пароль'
                    errorLabel.classes = 'text-sm text-red-600 mt-2'
                    return
                
                if not newPassword:
                    errorLabel.text = 'Введите новый пароль'
                    errorLabel.classes = 'text-sm text-red-600 mt-2'
                    return
                
                if not confirmPassword:
                    errorLabel.text = 'Подтвердите новый пароль'
                    errorLabel.classes = 'text-sm text-red-600 mt-2'
                    return
                
                # Проверка совпадения паролей (используем функцию проверки)
                if not check_passwords_match(show_error=False):
                    errorLabel.text = 'Пароли не совпадают'
                    errorLabel.classes = 'text-sm text-red-600 mt-2'
                    return
                
                # Проверка требований к паролю
                checks = {
                    'length': len(newPassword) >= 8,
                    'upper': bool(re.search(r'[A-ZА-Я]', newPassword)),
                    'lower': bool(re.search(r'[a-zа-я]', newPassword)),
                    'digit': bool(re.search(r'\d', newPassword)),
                    'special': bool(re.search(r'[@#$%^&*()_+\-=\[\]{};\':"\\|,.<>\/?!]', newPassword))
                }
                
                if not all(checks.values()):
                    errorLabel.text = 'Новый пароль не соответствует требованиям'
                    errorLabel.classes = 'text-sm text-red-600 mt-2'
                    return
                
                if currentPassword == newPassword:
                    errorLabel.text = 'Новый пароль должен отличаться от текущего'
                    errorLabel.classes = 'text-sm text-red-600 mt-2'
                    return
                
                # Блокируем кнопку
                changePasswordButton.props('disable')
                changePasswordButton.text = 'Изменение пароля...'
                
                # Контейнер для результата
                result_container = {'result': None, 'error': None, 'done': False}
                
                # Создаем задачу для асинхронного выполнения
                async def change_password_async():
                    try:
                        # Используем LDAPAuthenticator для смены пароля
                        authenticator = LDAPAuthenticator()
                        result = await authenticator.change_password(
                            username=user.username,
                            current_password=currentPassword,
                            new_password=newPassword
                        )
                        result_container['result'] = result
                        result_container['done'] = True
                    except Exception as e:
                        logger.error(f"Ошибка при смене пароля: {e}", exc_info=True)
                        result_container['error'] = str(e)
                        result_container['done'] = True
                
                # Запускаем асинхронную задачу
                asyncio.create_task(change_password_async())
                
                # Используем таймер для проверки результата и обновления UI
                def check_and_update_ui():
                    if result_container['done']:
                        # Обновляем UI в правильном контексте
                        if result_container['result']:
                            result = result_container['result']
                            if result.get('success'):
                                successLabel.text = result.get('message', 'Пароль успешно изменен') + '. Вы будете перенаправлены на страницу входа через 3 секунды.'
                                successLabel.classes('text-sm text-green-600 mt-2')
                                
                                # Очищаем поля
                                currentPasswordInput.value = ''
                                newPasswordInput.value = ''
                                confirmPasswordInput.value = ''
                                update_password_strength('')
                                
                                # Очищаем сессию и перенаправляем на страницу логина
                                def logout_and_redirect():
                                    try:
                                        # Получаем токен
                                        try:
                                            clientIp = ui.context.client.request.client.host
                                        except:
                                            clientIp = 'unknown'
                                        
                                        token = token_storage.get_token(clientIp)
                                        if token:
                                            # Очищаем пароль из сессии перед удалением
                                            session = session_manager.get_session(token)
                                            if session and hasattr(session, 'camunda_password'):
                                                session.camunda_password = None
                                            session_manager.remove_session(token)
                                            token_storage.remove_token(clientIp)
                                        clear_last_token()
                                        
                                        logger.info(f"Сессия очищена после смены пароля для пользователя {user.username}")
                                    except Exception as e:
                                        logger.error(f"Ошибка при очистке сессии: {e}", exc_info=True)
                                    
                                    ui.navigate.to('/login')
                                
                                # Перенаправляем через 3 секунды
                                ui.timer(3.0, logout_and_redirect, once=True)
                            else:
                                errorLabel.text = result.get('message', 'Ошибка при смене пароля')
                                errorLabel.classes('text-sm text-red-600 mt-2')
                        elif result_container['error']:
                            errorLabel.text = f'Ошибка при смене пароля: {result_container["error"]}'
                            errorLabel.classes('text-sm text-red-600 mt-2')
                        
                        # Разблокируем кнопку
                        changePasswordButton.props(remove='disable')
                        changePasswordButton.text = 'Изменить пароль'
                        return False  # Останавливаем таймер
                    return True  # Продолжаем проверку
                
                # Запускаем таймер для проверки результата
                ui.timer(0.1, check_and_update_ui)
                    
 
