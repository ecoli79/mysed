import pydantic
import pytz
import json
from datetime import datetime
from typing import Optional, Any, List, Dict, Union
from pydantic import field_validator, model_validator


class User(pydantic.BaseModel):
    login: str
    first_name: str
    last_name: str
    email: Optional[str] = None


# Общий базовый класс для моделей, где нужно форматировать даты
class DateTimeFormattedModel(pydantic.BaseModel):
    @field_validator('*', mode='before')
    @classmethod
    def format_datetime_fields(cls, v: Any) -> Any:
        """
        Автоматически преобразует строковые даты в формате ISO
        в локальное время (Москва) и возвращает в виде 'DD.MM.YYYY HH:MM:SS'
        Применяется ко ВСЕМ полям модели.
        """
        if not isinstance(v, str):
            return v  # Пропускаем, если не строка

        # Проверяем, похоже ли значение на ISO-дату (упрощённо)
        iso_like = (
            v.startswith(('20', '19')) and  # Год
            ('T' in v or ' ' in v) and     # Разделитель
            any(c in v for c in [':', '+', 'Z'])  # Время или TZ
        )
        if not iso_like:
            return v  # Не пытаемся парсить, если не похоже на дату

        try:
            # Заменяем 'Z' на '+00:00' для корректного парсинга
            parsed_dt = datetime.fromisoformat(v.replace('Z', '+00:00'))
            moscow_tz = pytz.timezone('Europe/Moscow')
            local_dt = parsed_dt.astimezone(moscow_tz)
            return local_dt.strftime('%d.%m.%Y %H:%M:%S')
        except Exception as e:
            # Можно включить логирование при необходимости
            # print(f"Не удалось распарсить дату: {v}, ошибка: {e}")
            return v  # Возвращаем как есть при ошибке
    
    @property
    def duration_formatted(self) -> str:
        """
        Возвращает duration (в мс) в читаемом виде: X ч Y мин Z сек
        Доступно, если модель имеет поле `duration`.
        """
        # Получаем duration, если поле существует
        duration_ms = getattr(self, 'duration', None)
        if duration_ms is None:
            return "N/A"

        total_seconds = int(duration_ms) // 1000
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours > 0:
            return f"{hours} ч {minutes} мин {seconds} сек"
        elif minutes > 0:
            return f"{minutes} мин {seconds} сек"
        else:
            return f"{seconds} сек"

    def model_dump(self, *args, **kwargs):
        """
        Дополнительно включаем `duration_formatted` в вывод,
        если используется сериализация.
        """
        data = super().model_dump(*args, **kwargs)
        # Добавляем formatted-поле, если есть duration
        if hasattr(self, 'duration'):
            data['duration_formatted'] = self.duration_formatted
        return data

    class Config:
        populate_by_name = True
        extra = "allow"

class JSONStringField(pydantic.BaseModel):
    """
    Специальное поле для работы с JSON строками, содержащими русские символы.
    Автоматически обрабатывает кодировку при сериализации/десериализации.
    """
    value: str
    
    @field_validator('value', mode='before')
    @classmethod
    def decode_json_string(cls, v: Any) -> str:
        """Декодирует JSON строку с правильной кодировкой"""
        if isinstance(v, str):
            try:
                # Пытаемся распарсить как JSON
                parsed = json.loads(v)
                if isinstance(parsed, dict):
                    # Если это словарь, сериализуем обратно с ensure_ascii=False
                    return json.dumps(parsed, ensure_ascii=False)
                return v
            except (json.JSONDecodeError, TypeError):
                # Если не JSON, возвращаем как есть
                return v
        return str(v)
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразует JSON строку в словарь"""
        try:
            return json.loads(self.value)
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def get_user_comment(self, username: str) -> Optional[str]:
        """Получает комментарий конкретного пользователя"""
        data = self.to_dict()
        return data.get(username)
    
    def set_user_comment(self, username: str, comment: str) -> None:
        """Устанавливает комментарий для пользователя"""
        data = self.to_dict()
        data[username] = comment
        self.value = json.dumps(data, ensure_ascii=False)
    
    def get_user_completion_date(self, username: str) -> Optional[str]:
        """Получает дату завершения конкретного пользователя"""
        data = self.to_dict()
        return data.get(username)
    
    def set_user_completion_date(self, username: str, date: str) -> None:
        """Устанавливает дату завершения для пользователя"""
        data = self.to_dict()
        data[username] = date
        self.value = json.dumps(data, ensure_ascii=False)
    
    def get_user_status(self, username: str) -> Optional[str]:
        """Получает статус конкретного пользователя"""
        data = self.to_dict()
        return data.get(username)
    
    def set_user_status(self, username: str, status: str) -> None:
        """Устанавливает статус для пользователя"""
        data = self.to_dict()
        data[username] = status
        self.value = json.dumps(data, ensure_ascii=False)
    
    def get_user_completed(self, username: str) -> bool:
        """Проверяет, завершил ли пользователь задачу"""
        data = self.to_dict()
        return data.get(username, False)
    
    def set_user_completed(self, username: str, completed: bool) -> None:
        """Устанавливает статус завершения для пользователя"""
        data = self.to_dict()
        data[username] = completed
        self.value = json.dumps(data, ensure_ascii=False)


class ProcessVariables(pydantic.BaseModel):
    """
    Модель для работы с переменными процесса Camunda.
    Автоматически обрабатывает JSON поля с правильной кодировкой.
    """
    assignee_list: Optional[List[str]] = None
    assigneeList: Optional[List[str]] = None  # Алиас для Camunda
    total_users: Optional[int] = None
    totalUsers: Optional[int] = None  # Алиас для Camunda
    completed_tasks: Optional[int] = None
    completedTasks: Optional[int] = None  # Алиас для Camunda
    due_date: Optional[str] = None
    dueDate: Optional[str] = None  # Алиас для Camunda
    process_notes: Optional[str] = None
    processNotes: Optional[str] = None  # Алиас для Camunda
    process_start_time: Optional[str] = None
    processStartTime: Optional[str] = None  # Алиас для Camunda
    process_status: Optional[str] = None
    processStatus: Optional[str] = None  # Алиас для Camunda
    task_name: Optional[str] = None
    taskName: Optional[str] = None  # Алиас для Camunda
    task_description: Optional[str] = None
    taskDescription: Optional[str] = None  # Алиас для Camunda
    priority: Optional[int] = None
    
    # JSON поля с автоматической обработкой кодировки
    user_completion_dates: Optional[JSONStringField] = None
    userCompletionDates: Optional[JSONStringField] = None  # Алиас для Camunda
    user_comments: Optional[JSONStringField] = None
    userComments: Optional[JSONStringField] = None  # Алиас для Camunda
    user_status: Optional[JSONStringField] = None
    userStatus: Optional[JSONStringField] = None  # Алиас для Camunda
    user_completed: Optional[JSONStringField] = None
    userCompleted: Optional[JSONStringField] = None  # Алиас для Camunda
    process_creator: Optional[str] = None
    processCreator: Optional[str] = None  # Алиас для Camunda
    creator_name: Optional[str] = None
    creatorName: Optional[str] = None  # Алиас для Camunda
    creator_email: Optional[str] = None
    creatorEmail: Optional[str] = None  # Алиас для Camunda
    
    @field_validator('user_completion_dates', 'user_comments', 'user_status', 'user_completed',
                    'userCompletionDates', 'userComments', 'userStatus', 'userCompleted', mode='before')
    @classmethod
    def parse_json_fields(cls, v: Any) -> Optional[JSONStringField]:
        """Парсит JSON поля из строк"""
        if isinstance(v, str):
            return JSONStringField(value=v)
        elif isinstance(v, dict):
            return JSONStringField(value=json.dumps(v, ensure_ascii=False))
        elif v is None:
            return JSONStringField(value='{}')
        return v
    
    @field_validator('assignee_list', 'assigneeList', mode='before')
    @classmethod
    def parse_assignee_list(cls, v: Any) -> Optional[List[str]]:
        """Парсит список пользователей из JSON строки"""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, TypeError):
                return []
        elif isinstance(v, list):
            return v
        return None
    
    def get_user_info(self, username: str) -> Dict[str, Any]:
        """Получает полную информацию о пользователе"""
        # Используем алиасы для Camunda
        user_comments = self.userComments or self.user_comments
        user_completion_dates = self.userCompletionDates or self.user_completion_dates
        user_status = self.userStatus or self.user_status
        user_completed = self.userCompleted or self.user_completed
        
        return {
            'username': username,
            'comment': user_comments.get_user_comment(username) if user_comments else None,
            'completion_date': user_completion_dates.get_user_completion_date(username) if user_completion_dates else None,
            'status': user_status.get_user_status(username) if user_status else None,
            'completed': user_completed.get_user_completed(username) if user_completed else False
        }
    
    def update_user_info(self, username: str, comment: Optional[str] = None, 
                        completion_date: Optional[str] = None, 
                        status: Optional[str] = None, 
                        completed: Optional[bool] = None) -> None:
        """Обновляет информацию о пользователе"""
        # Используем алиасы для Camunda
        user_comments = self.userComments or self.user_comments
        user_completion_dates = self.userCompletionDates or self.user_completion_dates
        user_status = self.userStatus or self.user_status
        user_completed = self.userCompleted or self.user_completed
        
        # Инициализируем поля, если они None
        if comment is not None:
            if not user_comments:
                user_comments = JSONStringField(value="{}")
                self.user_comments = user_comments
                self.userComments = user_comments
            user_comments.set_user_comment(username, comment)
        
        if completion_date is not None:
            if not user_completion_dates:
                user_completion_dates = JSONStringField(value="{}")
                self.user_completion_dates = user_completion_dates
                self.userCompletionDates = user_completion_dates
            user_completion_dates.set_user_completion_date(username, completion_date)
        
        if status is not None:
            if not user_status:
                user_status = JSONStringField(value="{}")
                self.user_status = user_status
                self.userStatus = user_status
            user_status.set_user_status(username, status)
        
        if completed is not None:
            if not user_completed:
                user_completed = JSONStringField(value="{}")
                self.user_completed = user_completed
                self.userCompleted = user_completed
            user_completed.set_user_completed(username, completed)


class Task(DateTimeFormattedModel):
    id: Optional[str] = None
    processDefinitionKey: str
    processDefinitionId: str
    processInstanceId: str
    executionId: str
    caseDefinitionKey: str
    caseDefinitionId: str
    caseInstanceId: str
    caseExecutionId: str
    activityInstanceId: str
    name: str
    description: str
    deleteReason: str
    owner: str
    assignee: str
    startTime: str
    endTime: Optional[str] = None
    duration: Optional[int] = None
    taskDefinitionKey: str
    priority: int
    due: Optional[str] = None
    parentTaskId: Optional[str] = None
    followUp: Optional[str] = None
    tenantId: Optional[str] = None
    removalTime: Optional[str] = None
    rootProcessInstanceId: Optional[str] = None
    taskState: str
    due_date: Optional[str] = None
  

# Camunda Models
class CamundaProcessDefinition(pydantic.BaseModel):
    id: str
    key: str
    category: Optional[str] = None
    description: Optional[str] = None
    name: str
    version: int
    resource: str
    deployment_id: str
    diagram: Optional[str] = None
    suspended: bool
    tenant_id: Optional[str] = None
    version_tag: Optional[str] = None
    history_time_to_live: Optional[int] = None
    startable_in_tasklist: bool

class CamundaDeployment(pydantic.BaseModel):
    id: str
    name: str
    deployment_time: str
    source: Optional[str] = None
    tenant_id: Optional[str] = None
    process_definitions: Optional[List[CamundaProcessDefinition]] = []

class CamundaTask(DateTimeFormattedModel):
    id: str
    name: str
    assignee: Optional[str] = None
    start_time: str
    due: Optional[str] = None
    follow_up: Optional[str] = None
    delegation_state: Optional[str] = None
    description: Optional[str] = None
    execution_id: str
    owner: Optional[str] = None
    parent_task_id: Optional[str] = None
    priority: int
    process_definition_id: str
    process_instance_id: str
    task_definition_key: str
    case_execution_id: Optional[str] = None
    case_instance_id: Optional[str] = None
    case_definition_id: Optional[str] = None
    suspended: bool
    form_key: Optional[str] = None
    tenant_id: Optional[str] = None

class CamundaHistoryTask(DateTimeFormattedModel):
    id: str
    process_definition_key: str
    process_definition_id: str
    process_instance_id: str
    execution_id: str
    case_definition_key: Optional[str] = None
    case_definition_id: Optional[str] = None
    case_instance_id: Optional[str] = None
    case_execution_id: Optional[str] = None
    activity_instance_id: str
    name: str
    description: Optional[str] = None
    delete_reason: Optional[str] = None
    owner: Optional[str] = None
    assignee: Optional[str] = None
    start_time: str
    end_time: Optional[str] = None
    duration: Optional[int] = None
    task_definition_key: str
    priority: int
    due: Optional[str] = None
    parent_task_id: Optional[str] = None
    follow_up: Optional[str] = None
    tenant_id: Optional[str] = None
    removal_time: Optional[str] = None
    root_process_instance_id: Optional[str] = None

class CamundaDeploymentRequest(pydantic.BaseModel):
    deployment_name: str
    enable_duplicate_filtering: bool = False
    deploy_changed_only: bool = False
    deployment_source: Optional[str] = None
    tenant_id: Optional[str] = None

class CamundaTaskAssignment(pydantic.BaseModel):
    assignee: str
    task_id: str

class CamundaTaskCompletion(pydantic.BaseModel):
    task_id: str
    variables: Optional[dict] = None

class TaskResult(DateTimeFormattedModel):
    """Модель результата выполнения задачи"""
    task_id: str
    process_instance_id: str
    assignee: str
    completion_date: str
    status: str  # completed, rejected, cancelled
    comment: Optional[str] = None
    result_files: List[Dict[str, Any]] = []  # Список загруженных файлов
    variables: Dict[str, Any] = {}  # Переменные процесса
    mayan_document_id: Optional[str] = None  # ID документа в Mayan EDMS

class TaskResultFile(pydantic.BaseModel):
    """Модель файла результата выполнения задачи"""
    filename: str
    mimetype: str
    size: int
    mayan_document_id: str
    download_url: str
    upload_date: str
    description: Optional[str] = None

class TaskCompletionRequest(pydantic.BaseModel):
    """Модель запроса на завершение задачи"""
    task_id: str
    status: str  # completed, rejected, cancelled
    comment: Optional[str] = None
    files: List[Dict[str, Any]] = []  # Файлы для загрузки
    variables: Dict[str, Any] = {}  # Дополнительные переменные

# ===== МОДЕЛИ ДЛЯ СИСТЕМЫ АВТОРИЗАЦИИ =====

class LoginRequest(pydantic.BaseModel):
    """Модель запроса на вход в систему"""
    username: str
    password: str

class UserSession(DateTimeFormattedModel):
    """Модель сессии пользователя"""
    user_id: str
    username: str
    first_name: str
    last_name: str
    email: Optional[str] = None
    groups: List[str] = []
    login_time: str  # Будет автоматически форматироваться
    last_activity: str  # Будет автоматически форматироваться
    is_active: bool = True
    mayan_api_token: Optional[str] = None # API токен для Mayan EDMS

class AuthResponse(pydantic.BaseModel):
    """Модель ответа аутентификации"""
    success: bool
    message: str
    user: Optional[UserSession] = None
    token: Optional[str] = None

class LDAPUser(pydantic.BaseModel):
    """Модель пользователя из LDAP"""
    dn: str
    uid: str
    cn: str
    givenName: str
    sn: str
    mail: Optional[str] = None
    memberOf: List[str] = []
    userPassword: Optional[str] = None

class UserGroup(pydantic.BaseModel):
    """Модель группы пользователей"""
    cn: str
    description: Optional[str] = None
    memberUid: List[str] = []
    is_dynamic: bool = False
    group_type: str = "static"  # static, dynamic

class SessionInfo(DateTimeFormattedModel):
    """Модель информации о сессии"""
    token: str
    user: UserSession
    expires_at: str  # Будет автоматически форматироваться
    is_expired: bool = False

class AuthError(pydantic.BaseModel):
    """Модель ошибки аутентификации"""
    error_code: str
    error_message: str
    details: Optional[Dict[str, Any]] = None

class PasswordChangeRequest(pydantic.BaseModel):
    """Модель запроса на смену пароля"""
    current_password: str
    new_password: str
    confirm_password: str

class UserProfile(DateTimeFormattedModel):
    """Модель профиля пользователя"""
    user_id: str
    username: str
    first_name: str
    last_name: str
    email: Optional[str] = None
    groups: List[str] = []
    last_login: Optional[str] = None  # Будет автоматически форматироваться
    is_active: bool = True
    created_at: Optional[str] = None  # Будет автоматически форматироваться
    updated_at: Optional[str] = None  # Будет автоматически форматироваться

class Permission(pydantic.BaseModel):
    """Модель разрешения"""
    name: str
    description: Optional[str] = None
    resource: str  # например: 'tasks', 'documents', 'admin'
    action: str    # например: 'read', 'write', 'delete', 'manage'

class Role(pydantic.BaseModel):
    """Модель роли"""
    name: str
    description: Optional[str] = None
    permissions: List[Permission] = []
    is_system: bool = False  # системная роль (нельзя удалить)

class UserRole(DateTimeFormattedModel):
    """Модель роли пользователя"""
    user_id: str
    role_name: str
    assigned_at: str  # Будет автоматически форматироваться
    assigned_by: str
    expires_at: Optional[str] = None  # Будет автоматически форматироваться


class UserTaskInfo(DateTimeFormattedModel):
    """Информация о задаче для конкретного пользователя"""
    task_id: str
    assignee: str
    start_time: str
    end_time: Optional[str] = None
    duration: Optional[int] = None
    status: str  # 'completed', 'in_progress'
    comment: Optional[str] = None
    review_date: Optional[str] = None
    
    @classmethod
    def from_process_variables(cls, task_id: str, assignee: str, 
                             start_time: str, end_time: Optional[str],
                             duration: Optional[int], process_variables: ProcessVariables) -> 'UserTaskInfo':
        """Создает UserTaskInfo из переменных процесса"""
        user_info = process_variables.get_user_info(assignee)
        
        return cls(
            task_id=task_id,
            assignee=assignee,
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            status=user_info['status'] or 'in_progress',
            comment=user_info['comment'],
            review_date=user_info['completion_date']
        )


class GroupedHistoryTask(DateTimeFormattedModel):
    """Группированная историческая задача (для multi-user задач)"""
    process_instance_id: str
    name: str
    description: Optional[str] = None
    process_definition_key: str
    process_definition_id: str
    priority: int
    due: Optional[str] = None
    start_time: str
    end_time: Optional[str] = None
    duration: Optional[int] = None
    total_users: int
    completed_users: int
    user_tasks: List[UserTaskInfo] = []
    is_multi_instance: bool = True
    
    @property
    def is_completed(self) -> bool:
        """Проверяет, завершена ли задача всеми пользователями"""
        return self.completed_users >= self.total_users
    
    @property
    def completion_percent(self) -> float:
        """Возвращает процент завершения"""
        if self.total_users == 0:
            return 0.0
        return (self.completed_users / self.total_users) * 100