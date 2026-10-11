"""
Лабораторная работа: клиент для SampleAPIs Coffee.

Создание: POST https://api.sampleapis.com/coffee/hot.
Заголовки: Content-Type: application/json (requests добавляет его для json=),
Accept: application/json.

JSON-тело:
- title (строка) — название с уникальной меткой группы;
- description (строка) — описание;
- ingredients (массив строк) — ингредиенты;
- image (строка) — URL изображения.

Для этого запроса считаем обязательными все четыре поля: POST только с title вернул
400 и показал ожидаемую схему. Отсутствие каждого поля по отдельности не проверялось;
необязательные поля не установлены. Пустая строка image принята, другие ограничения
на значения не исследовались. Эти четыре поля задаёт клиент, числовой id добавляет
сервер.

Ожидаемый успех POST: 201 и JSON-объект с отправленными полями и id.

Подтверждено запросами: GET коллекции/ресурса — 200, POST — 201, PUT/PATCH/DELETE —
200; отсутствующий ресурс возвращает 404. PATCH сохраняет неуказанные поля.
Клиент дополнительно проверяет статусы и JSON-формат ответов, тип id и совпадение
сохранённых полей с отправленными. Эти проверки относятся к клиенту, а не к правилам
валидации значений на сервере.
"""

import requests
from uuid import uuid4

JsonObject = dict[str, object]


class CoffeeApiError(Exception):
    pass


class CoffeeNotFoundError(CoffeeApiError):
    pass


class CoffeeRequestTimeoutError(CoffeeApiError):
    pass


class SampleApisCoffeeClient:
    def __init__(
        self,
        base_url: str = "https://api.sampleapis.com/coffee/hot",
        timeout: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def list_drinks(self) -> list[JsonObject]:
        response = self._request("GET")
        self._expect_status(response, 200, "GET коллекции")
        try:
            data = response.json()
        except requests.exceptions.JSONDecodeError as error:
            raise CoffeeApiError(f"Некорректный JSON в ответе GET коллекции: {error}") from error
        if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
            raise CoffeeApiError("Ожидался JSON-массив напитков")
        return data

    def get_drink(self, drink_id: int) -> JsonObject:
        response = self._request("GET", f"/{drink_id}")
        self._expect_status(response, 200, f"GET id={drink_id}")
        return self._json_object(response, f"GET id={drink_id}")

    def create_drink(self, payload: JsonObject) -> JsonObject:
        response = self._request("POST", payload=payload)
        self._expect_status(response, 201, "POST")
        return self._json_object(response, "POST")

    def replace_drink(self, drink_id: int, payload: JsonObject) -> JsonObject:
        response = self._request("PUT", f"/{drink_id}", payload=payload)
        self._expect_status(response, 200, f"PUT id={drink_id}")
        return self._json_object(response, f"PUT id={drink_id}")

    def update_drink(self, drink_id: int, changes: JsonObject) -> JsonObject:
        response = self._request("PATCH", f"/{drink_id}", payload=changes)
        self._expect_status(response, 200, f"PATCH id={drink_id}")
        return self._json_object(response, f"PATCH id={drink_id}")

    def delete_drink(self, drink_id: int) -> None:
        response = self._request("DELETE", f"/{drink_id}")
        self._expect_status(response, 200, f"DELETE id={drink_id}")

    def _request(
        self,
        method: str,
        path: str = "",
        payload: JsonObject | None = None,
    ) -> requests.Response:
        """Отправляет запрос и проверяет HTTP-ответ."""
        url = f"{self._base_url}{path}"

        try:
            response = requests.request(
                method,
                url,
                json=payload,
                headers={"Accept": "application/json"},
                timeout=self._timeout,
            )
        except requests.Timeout as error:
            raise CoffeeRequestTimeoutError(f"Тайм-аут запроса к {url}: {error}") from error
        except requests.RequestException as error:
            raise CoffeeApiError(f"Сетевая ошибка при запросе к {url}: {error}") from error

        if response.status_code == 404:
            raise CoffeeNotFoundError(f"Ресурс не найден: {url}")

        if response.status_code >= 400:
            error_msg = f"HTTP ошибка {response.status_code}"
            if self._is_json(response):
                try:
                    err_data = response.json()
                    error_msg += f": {err_data}"
                except requests.exceptions.JSONDecodeError:
                    error_msg += f": некорректный JSON: {response.text[:100]}"
            else:
                error_msg += f": {response.text[:100]}"
            raise CoffeeApiError(error_msg)

        if response.status_code != 204:
            if not self._is_json(response):
                content_type = response.headers.get("Content-Type", "не указан")
                raise CoffeeApiError(f"Ожидался JSON, но получен Content-Type: {content_type}")

        return response

    @staticmethod
    def _is_json(response: requests.Response) -> bool:
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        return content_type == "application/json" or content_type.endswith("+json")

    @staticmethod
    def _expect_status(response: requests.Response, expected: int, operation: str) -> None:
        if response.status_code != expected:
            raise CoffeeApiError(
                f"{operation}: ожидался HTTP {expected}, получен {response.status_code}"
            )

    @staticmethod
    def _json_object(response: requests.Response, operation: str) -> JsonObject:
        try:
            data = response.json()
        except requests.exceptions.JSONDecodeError as error:
            raise CoffeeApiError(f"{operation}: некорректный JSON: {error}") from error
        if not isinstance(data, dict):
            raise CoffeeApiError(f"{operation}: ожидался JSON-объект")
        return data


def main() -> int:
    client = SampleApisCoffeeClient()
    marker = uuid4().hex[:8]
    created_id: int | None = None
    delete_attempted = False

    print(f"--- Начало сценария. Метка группы: {marker} ---\n")

    try:
        print("1. Получаем список горячих напитков...")
        drinks = client.list_drinks()
        print(f"   Успешно. Найдено напитков: {len(drinks)}")

        print("\n2. Создаем новый напиток...")
        new_drink_payload = {
            "title": f"Lab1 Test Coffee {marker}",
            "description": "Created for workshop",
            "ingredients": ["espresso", "water"],
            "image": "",
        }
        try:
            created_drink = client.create_drink(new_drink_payload)
        except CoffeeRequestTimeoutError as error:
            print(f"   Тайм-аут POST: результат создания неизвестен: {error}")
            print(f"   Не повторяйте POST. Метка для ручной проверки: {marker}")
            return 1
        returned_id = created_drink.get("id")
        if not isinstance(returned_id, int) or isinstance(returned_id, bool):
            raise CoffeeApiError("POST не вернул числовой id созданного напитка")
        created_id = returned_id
        print(f"   Успешно. Создан напиток с id={created_id}")

        print("\n3. Получаем созданный напиток по id...")
        fetched_drink = client.get_drink(created_id)
        _verify_fields(fetched_drink, new_drink_payload, "GET после POST")
        print("   Успешно. Все отправленные поля совпадают.")

        print("\n4. Полностью заменяем данные напитка (PUT)...")
        replaced_payload = {
            "title": f"Replaced Coffee {marker}",
            "description": "Fully replaced via PUT",
            "ingredients": ["cold brew"],
            "image": "",
        }
        client.replace_drink(created_id, replaced_payload)
        after_put = client.get_drink(created_id)
        _verify_fields(after_put, replaced_payload, "GET после PUT")
        if after_put.get("id") != created_id:
            raise CoffeeApiError("id изменился после PUT")
        print("   Успешно. Все заменённые поля проверены через GET.")

        print("\n5. Частично изменяем напиток (PATCH)...")
        patch_changes = {"description": "Updated with PATCH"}
        client.update_drink(created_id, patch_changes)
        print("   PATCH успешно выполнен.")

        print("\n6. Проверяем изменения через повторный GET...")
        verified_drink = client.get_drink(created_id)
        _verify_fields(verified_drink, {**replaced_payload, **patch_changes}, "GET после PATCH")
        if verified_drink.get("id") != created_id:
            raise CoffeeApiError("id изменился после PATCH")
        print("   Успешно. Новое описание сохранено, остальные поля не изменились.")

        print("\n7. Удаляем созданный напиток...")
        delete_attempted = True
        client.delete_drink(created_id)
        print("   Успешно. DELETE вернул ожидаемый HTTP 200.")

        print("\n8. Проверяем удаление (ожидаем 404)...")
        try:
            client.get_drink(created_id)
        except CoffeeNotFoundError:
            print("   Успешно. Получен ожидаемый 404 Not Found.")
            created_id = None
        else:
            raise CoffeeApiError("После DELETE ресурс всё ещё доступен")

    except CoffeeNotFoundError as e:
        print(f"Ошибка отсутствия ресурса: {e}")
        print(f"Метка группы для ручной проверки: {marker}")
        return 1
    except CoffeeApiError as e:
        print(f"Ошибка API: {e}")
        print(f"Метка группы для ручной проверки: {marker}")
        return 1
    except Exception as e:
        print(f"Неожиданная ошибка: {e}")
        print(f"Метка группы для ручной проверки: {marker}")
        return 1
    finally:
        if created_id is not None and not delete_attempted:
            print("Очистка: удаляем созданный ресурс...")
            try:
                client.delete_drink(created_id)
                print("   Созданный ресурс удалён.")
            except CoffeeNotFoundError:
                print("   Созданный ресурс уже отсутствует.")
            except CoffeeApiError as error:
                print(f"   Не удалось удалить id={created_id}: {error}")

    print("--- Сценарий успешно завершён ---")
    return 0


def _verify_fields(actual: JsonObject, expected: JsonObject, operation: str) -> None:
    for key, expected_value in expected.items():
        if actual.get(key) != expected_value:
            raise CoffeeApiError(
                f"{operation}: поле {key!r}: ожидалось {expected_value!r}, "
                f"получено {actual.get(key)!r}"
            )


if __name__ == "__main__":
    raise SystemExit(main())