# TASK111 — аудит 10 источников дополнительной спецификации

Дата проверки: 2026-09-04

## Решение

В рабочем пуле используются **10 нероссийских источников**. Сервис не обязан
опросить все десять для каждой машины: после точного определения VIN-семейства
он обращается к применимым каталогам, а остальные фиксирует как неприменимые.
Для нового неизвестного семейства поиск выполняется по всему пулу.

| Приоритет | Источник | Основная роль |
|---:|---|---|
| 100 | `vpic.nhtsa.dot.gov` | Официальный VIN-декодер и строгая проверка идентичности |
| 96 | `auto.danawa.com` | Корейские заводские таблицы поколений и LPi-комплектаций |
| 94 | `carwiki.co.kr` | Корейские K5/Sonata по году, двигателю и топливу |
| 91 | `carisyou.com` | Дополнительная проверка корейского поколения/комплектации |
| 90 | `auto-data.net` | Подробные точные европейские и международные модификации |
| 82 | `ultimatespecs.com` | Независимое подтверждение динамики, размеров и расхода |
| 80 | `automobile-catalog.com` | Подтверждение старых европейских модификаций |
| 76 | `cars-data.com` | Подтверждение B-Class W245 и геометрии |
| 75 | `carfolio.com` | Точные карточки Sonata LPi и европейских моделей |
| 70 | `encycarpedia.com` | Резервная проверка динамики и размеров |

## Контрольные страницы

- NHTSA vPIC API: <https://vpic.nhtsa.dot.gov/api/>
- E 220 d W213: <https://www.auto-data.net/en/mercedes-benz-e-class-w213-e-220d-194hp-9g-tronic-22636>
- B 170/B 180 W245: <https://www.auto-data.net/en/mercedes-benz-b-class-w245-facelift-2008-b-170-116hp-autotronic-12508>
- B 180 CDI W246: <https://www.auto-data.net/en/mercedes-benz-b-class-w246-b-180-1.8-cdi-109hp-7g-dct-18833>
- B 200 CDI W246: <https://www.auto-data.net/en/mercedes-benz-b-class-w246-facelift-2014-b-200-cdi-136hp-dct-20881>
- Optima/K5 1.7 CRDi DCT: <https://www.auto-data.net/en/kia-optima-iv-1.7-crdi-141hp-dct-22795>
- K5 2.0 LPi: <https://www.carwiki.co.kr/model/10032_2018/%EB%8D%94_%EB%89%B4_K5_2%EC%84%B8%EB%8C%80>
- K5 Danawa: <https://auto.danawa.com/auto/?Lineup=42280&Model=3260%2C3151&Tab=spec&Work=model&pcUse=y>
- Sonata New Rise LPi Danawa: <https://auto.danawa.com/auto/modelPopup.php?Lineup=42773&Type=spec>
- Sonata New Rise CarWiki: <https://www.carwiki.co.kr/model/10004/%EC%8F%98%EB%82%98%ED%83%80_%EB%89%B4_%EB%9D%BC%EC%9D%B4%EC%A6%88>
- Sonata LPi Carfolio: <https://www.carfolio.com/hyundai-sonata-2.0-lpi-automatic-854447>
- B-Class UltimateSpecs: <https://www.ultimatespecs.com/car-specs/Mercedes-Benz/24345/Mercedes-Benz-B-Class-%28W245%29-B180-Autotronic.html>
- B-Class Automobile-Catalog: <https://www.automobile-catalog.com/car/2010/1549490/mercedes-benz_b_180_autotronic.html>
- B-Class Cars-Data: <https://cars-data.com/en/mercedes-benz/b-class/w245/b-170-35607--35607/specs>
- B 170 Carfolio: <https://www.carfolio.com/mercedes-benz-b-170-178288>
- B 170 EncyCARpedia: <https://www.encycarpedia.com/mercedes/05-b-170-mpv>

## Барьеры качества

- Профиль выбирается по точному VIN-префиксу плюс марке, модели, топливу и
  диапазону объёма двигателя; одного совпадения названия недостаточно.
- Значение года из VIN расширяет окно поиска, но не меняет поле года в CRM.
- vPIC-факты принимаются только после совпадения марки, модели и одного из
  допустимых модельных годов.
- В конфликте выигрывает наиболее приоритетный применимый источник, а не
  случайное большинство низкоприоритетных агрегаторов.
- Точные подтверждённые значения хранятся как версионированный каталог с URL
  происхождения, чтобы блокировка или JavaScript источника не оставляли
  карточку пустой.
- Ручная правка менеджера всегда имеет приоритет над автоматическим значением.
- Основные поля CRM, цены, стоимость, аукционные и коммерческие сведения
  отбрасываются до записи.
- URL и происхождение фактов остаются во внутреннем sidecar и не выводятся
  клиенту.
