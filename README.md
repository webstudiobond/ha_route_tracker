[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

# Home Assistant Route Tracker

Компонент для отслеживания и визуализации маршрутов устройств в Home Assistant. Основан на [ha_routes mavrikkk](https://github.com/mavrikkk/ha_routes)

Используются: библиотека [Leaflet](https://app.unpkg.com/leaflet@1.9.4/files/dist), а также плагин [leaflet.polylineDecorator.js](https://raw.githubusercontent.com/bbecquet/Leaflet.PolylineDecorator/refs/heads/master/dist/leaflet.polylineDecorator.js)

> :warning: **ВНИМАНИЕ:**  
>
> Не рекомендуется использовать в недоверенной сети!
> 
> Все данные доступны без авторизации по пути `https://your-ha-url.com/local/route`
> Для безопасного использования необходимо закрыть данный путь в обратном прокси сервере.

## 1. Установка
**Способ 1. Добавить в HACS**

Перейдите на страницу "Интеграции" в HACS и выберите три точки в правом верхнем углу. Выберите Пользовательские репозитории. Добавьте url репозитория. Тип - Интеграция. Подробнее в [документации HACS](https://hacs.xyz/docs/faq/custom_repositories).

**Способ 2. Ручной**

Содержимое папки `route` скопировать в директорию `config_folder_homeassistant/custom_components/route`.

## 2. О device_tracker
API Home Assistant устроен так, что позволяет получать историю только при изменении состояний. 
Так как состоянием у `device_tracker` является расположение в какой-либо зоне или `not_home`, то и координаты будут не все, а только те, которые зафиксированы при смене состояний. 
Чтобы этого избежать компонент создает в HA новый виртуальный сенсор `sensor.virtual_device_tracker_entity_id`, у которого в атрибуты копируются данные из нужного `device_tracker.entity_id`, а состоянием будет `last_updated`.

## 3. Настройка
Добавьте в ваш файл конфигурации "configuration.yaml" подобные строки:
```yaml
route:
  - name: "Семейные маршруты"
    devices:
      - ["Название устройства", "device_tracker.entity_id"]
      - ["Мой телефон", "device_tracker.my_phone"]
    hlat: 50.4501
    hlon: 30.5234
    haddr: "https://your-ha-url.com"
    access_token: "your_Long_term_access_token"
    time_zone: "Europe/London"
    minimal_distance: 0.05
    number_of_days: 14
```
**Здесь:**
- `devices` - список устройств в формате [отображаемое_имя, entity_id]
- `hlat` / `hlon` - координаты (широта и долгота) вашего дома (центр карты по умолчанию)
- `haddr` - должен быть ваш реальный URL Home Assistant
- `access_token` - нужно создать долгосрочный токен доступа в профиле HA
- `time_zone` -  часовой пояс
- `minimal_distance` - минимальная дистанция
- `number_of_days` - количество дней, для выбора из истории

**Как получить токен доступа:**
1. Перейдите в Профиль → Безопасность → Долгосрочные токены доступа
2. Создайте "Долгосрочный токен доступа"
3. Скопируйте токен в конфигурацию

**После настройки**
1. Откройте в боковой панели.
2. Или перейдите в браузере по адресу: `https://your-ha-url.com/local/route`

> :warning: **ВНИМАНИЕ:**  
> Если Home Assistant доступен вне локальной сети / вне доверенной сети, то для безопасности нужно дополнительно закрыть путь `/local/route` или весь `/local/` неавторизированным посетителям.

**Пример для nginx**
```
# Upgrade WebSocket if requested, otherwise use keepalive
map $http_upgrade $connection_upgrade_keepalive {
    default upgrade;
    ''      '';
}
server {
...
  location /local/ {
        allow 192.168.100.7; # локальная сеть
        allow 1.2.3.4; # ваш внешний белый IP (это может быть, например, ваш IP своего VPN)
        deny all;

        proxy_pass http://127.0.0.1:8123;
        proxy_redirect      off;
        proxy_set_header    X-Real-IP           $remote_addr;
        proxy_set_header    X-Forwarded-For     $proxy_add_x_forwarded_for;
        proxy_set_header    X-Forwarded-Proto   $scheme;
        proxy_set_header    Host                $http_host;
        proxy_set_header    X-NginX-Proxy       true;
        proxy_http_version  1.1;
        proxy_set_header    Upgrade             $http_upgrade;
        proxy_set_header    Connection          $connection_upgrade_keepalive;
  }
  location / {
        proxy_pass http://127.0.0.1:8123;
        proxy_redirect      off;
        proxy_set_header    X-Real-IP           $remote_addr;
        proxy_set_header    X-Forwarded-For     $proxy_add_x_forwarded_for;
        proxy_set_header    X-Forwarded-Proto   $scheme;
        proxy_set_header    Host                $http_host;
        proxy_set_header    X-NginX-Proxy       true;
        proxy_http_version  1.1;
        proxy_set_header    Upgrade             $http_upgrade;
        proxy_set_header    Connection          $connection_upgrade_keepalive;
  }
...
}
```
