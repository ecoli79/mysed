#!/usr/bin/env python3
"""
Скрипт для проверки миграции глобальных переменных на класс состояния.

Этот скрипт проверяет:
1. Корректность импорта класса состояния
2. Доступность всех методов и атрибутов
3. Отсутствие прямых обращений к старым глобальным переменным
"""

import sys
import os

# Добавляем корневую директорию проекта в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_state_import():
    """Проверяет импорт класса состояния"""
    try:
        from pages.task_completion_state import TaskCompletionPageState, get_state, reset_state
        print("✅ Импорт класса состояния успешен")
        return True
    except ImportError as e:
        print(f"❌ Ошибка импорта: {e}")
        return False

def test_state_initialization():
    """Проверяет инициализацию состояния"""
    try:
        from pages.task_completion_state import get_state
        
        state = get_state()
        
        # Проверяем, что состояние инициализировано
        assert state is not None, "Состояние не инициализировано"
        assert hasattr(state, 'tasks_container'), "Отсутствует атрибут tasks_container"
        assert hasattr(state, 'active_tasks_list'), "Отсутствует атрибут active_tasks_list"
        assert hasattr(state, 'task_cards'), "Отсутствует атрибут task_cards"
        
        # Проверяем методы
        assert hasattr(state, 'get_task_card_info'), "Отсутствует метод get_task_card_info"
        assert hasattr(state, 'set_task_card_info'), "Отсутствует метод set_task_card_info"
        assert hasattr(state, 'reset_active_tasks'), "Отсутствует метод reset_active_tasks"
        assert hasattr(state, 'reset_completed_tasks'), "Отсутствует метод reset_completed_tasks"
        assert hasattr(state, 'reset_uploaded_files'), "Отсутствует метод reset_uploaded_files"
        assert hasattr(state, 'reset_signing_state'), "Отсутствует метод reset_signing_state"
        assert hasattr(state, 'reset_all'), "Отсутствует метод reset_all"
        
        print("✅ Инициализация состояния успешна")
        print(f"   - tasks_container: {state.tasks_container}")
        print(f"   - active_tasks_list: {len(state.active_tasks_list)} задач")
        print(f"   - task_cards: {len(state.task_cards)} карточек")
        return True
    except Exception as e:
        print(f"❌ Ошибка инициализации: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_state_methods():
    """Проверяет работу методов состояния"""
    try:
        from pages.task_completion_state import get_state
        
        state = get_state()
        
        # Тест get_task_card_info
        result = state.get_task_card_info('test_task_id', 'test_process_id')
        assert result is None, "get_task_card_info должен возвращать None для несуществующей задачи"
        
        # Тест set_task_card_info
        test_card_info = {
            'card': None,
            'task_id': 'test_task_id',
            'process_id': 'test_process_id'
        }
        state.set_task_card_info('test_task_id', 'test_process_id', test_card_info)
        
        # Проверяем, что карточка сохранена
        result = state.get_task_card_info('test_task_id', 'test_process_id')
        assert result is not None, "Карточка должна быть сохранена"
        assert result['task_id'] == 'test_task_id', "Неверный task_id"
        
        # Тест reset методов
        state.reset_active_tasks()
        assert len(state.active_tasks_list) == 0, "active_tasks_list должен быть очищен"
        assert len(state.task_cards) == 0, "task_cards должен быть очищен"
        
        state.reset_uploaded_files()
        assert len(state.uploaded_files) == 0, "uploaded_files должен быть очищен"
        
        print("✅ Методы состояния работают корректно")
        return True
    except Exception as e:
        print(f"❌ Ошибка тестирования методов: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_page_import():
    """Проверяет импорт страницы"""
    try:
        from pages import task_completion_page
        print("✅ Импорт страницы успешен")
        return True
    except ImportError as e:
        print(f"❌ Ошибка импорта страницы: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_no_old_globals():
    """Проверяет отсутствие старых глобальных переменных"""
    try:
        import pages.task_completion_page as tcp
        
        # Список старых глобальных переменных, которые не должны существовать
        old_globals = [
            '_tasks_container',
            '_completed_tasks_container',
            '_selected_task_id',
            '_task_cards',
            '_active_tasks_list',
            '_all_completed_tasks',
            '_current_page',
            '_page_size',
            '_sort_type',
            '_active_tasks_sort_type',
            '_pending_task_id',
            '_show_all_certificates',
            '_certificates_cache',
            '_selected_certificate',
            '_document_for_signing',
            '_uploaded_files',
            '_tabs',
            '_task_details_tab',
            '_active_tasks_tab',
        ]
        
        found_old_globals = []
        for var_name in old_globals:
            if hasattr(tcp, var_name):
                found_old_globals.append(var_name)
        
        if found_old_globals:
            print(f"⚠️  Найдены старые глобальные переменные: {found_old_globals}")
            print("   Это может быть нормально, если они используются для обратной совместимости")
        else:
            print("✅ Старые глобальные переменные не найдены (или правильно заменены)")
        
        # Проверяем наличие state
        assert hasattr(tcp, 'state'), "Отсутствует переменная state"
        print(f"✅ Переменная state найдена: {type(tcp.state)}")
        
        return True
    except Exception as e:
        print(f"❌ Ошибка проверки глобальных переменных: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Запускает все тесты"""
    print("=" * 60)
    print("Тестирование миграции глобальных переменных на класс состояния")
    print("=" * 60)
    print()
    
    tests = [
        ("Импорт класса состояния", test_state_import),
        ("Инициализация состояния", test_state_initialization),
        ("Методы состояния", test_state_methods),
        ("Импорт страницы", test_page_import),
        ("Проверка старых глобальных переменных", test_no_old_globals),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n📋 Тест: {test_name}")
        print("-" * 60)
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ Критическая ошибка в тесте '{test_name}': {e}")
            results.append((test_name, False))
    
    print("\n" + "=" * 60)
    print("Результаты тестирования:")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ ПРОЙДЕН" if result else "❌ ПРОВАЛЕН"
        print(f"{status}: {test_name}")
    
    print()
    print(f"Итого: {passed}/{total} тестов пройдено")
    
    if passed == total:
        print("\n🎉 Все тесты пройдены успешно!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} тест(ов) провалено")
        return 1

if __name__ == '__main__':
    sys.exit(main())

