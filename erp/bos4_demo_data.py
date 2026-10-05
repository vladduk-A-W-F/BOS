"""Demo company for BoS 4: synthetic metal-furniture maker with linked branches.

Source of structure: Microsoft AdventureWorks OLTP sample (github.com/microsoft/sql-server-samples,
samples/databases/adventure-works). From it we take material article numbers (Product.ProductNumber),
vendor roles, lead times and minimum lots (ProductVendor), and the production route
(Location: Frame Forming, Frame Welding, Debur and Polish, Paint, Final Assembly).
Names are translated into Ukrainian; finished goods, prices in UAH, quantities, people and
counterparties are synthetic. Bills of materials (PRODUCTS) are synthetic furniture compositions built
from those AdventureWorks articles; they are not taken from AdventureWorks BillOfMaterials, which
describes bicycles. No real company or client data.

AdventureWorks notice (MIT License):
Copyright (c) Microsoft Corporation.
Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
associated documentation files (the "Software"), to deal in the Software without restriction,
including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions: The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT
LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN
NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

COMPANY = {
    'name': 'Каркас Меблі · демо',
    'description': 'Виробництво металевих меблів для складів, майстерень і офісів',
    'industry': 'Металеві меблі',
}

# code, name, type, city, lat, lng (GeoNames city centres, CC BY 4.0; not real addresses)
BRANCHES = (
    ('KYI', 'Головний офіс', 'headquarters', 'Київ', 50.45466, 30.52380),
    ('ZHY', 'Виробництво', 'department', 'Житомир', 50.25465, 28.65867),
    ('LVI', 'Філія', 'regional', 'Львів', 49.83826, 24.02324),
    ('DNI', 'Філія', 'regional', 'Дніпро', 48.46664, 35.04066),
)

# key, branch, kind, name
LOCATIONS = (
    ('ZHY-METAL', 'ZHY', 'warehouse', 'Склад металу'),
    ('ZHY-SHOP', 'ZHY', 'production', 'Цех'),
    ('ZHY-FG', 'ZHY', 'warehouse', 'Склад готової продукції'),
    ('KYI-WH', 'KYI', 'warehouse', 'Склад-шоурум'),
    ('LVI-WH', 'LVI', 'warehouse', 'Склад'),
    ('DNI-WH', 'DNI', 'warehouse', 'Склад'),
)

# full name, role, department, branch
PEOPLE = (
    ('Олена Коваль', 'Комерційна директорка', 'Продажі', 'KYI'),
    ('Андрій Мельник', 'Менеджер з продажу', 'Продажі', 'KYI'),
    ('Ірина Лисенко', 'Бухгалтерка', 'Фінанси', 'KYI'),
    ('Ігор Бондар', 'Начальник виробництва', 'Виробництво', 'ZHY'),
    ('Наталія Ткаченко', 'Інженерка з якості', 'Якість', 'ZHY'),
    ('Сергій Кравець', 'Комірник', 'Склад', 'ZHY'),
    ("Мар'яна Гнатюк", 'Керівниця філії', 'Продажі', 'LVI'),
    ('Дмитро Савченко', 'Керівник філії', 'Продажі', 'DNI'),
)

# key, name, AdventureWorks vendor it stands for, city, lat, lng (GeoNames city centre, not an address)
SUPPLIERS = (
    ('METAL', 'Металопрокат Центр', 'Custom Frames, Inc.', 'Кривий Ріг', 47.91048, 33.39178),
    ('FAST', 'Кріплення Плюс', 'Cruger Bike Company', 'Харків', 49.98081, 36.25272),
    ('PAINT', 'Порошкові фарби Схід', 'Trey Research', 'Запоріжжя', 47.82289, 35.19031),
)

# key, name, city
CUSTOMERS = (
    ('LOGISTIC', 'ТОВ «Логістик Парк»', 'Київ'),
    ('OFFICE', 'ТОВ «Офіс Сіті»', 'Київ'),
    ('AGRO', 'ТОВ «Агроснаб Дніпро»', 'Дніпро'),
    ('AUTO', 'ПП «Автосервіс Захід»', 'Львів'),
    ('SCHOOL', 'Житомирський ліцей № 7', 'Житомир'),
)

# AW ProductNumber (kept as article), name, unit, supplier, price UAH, minimum, lead days, certificate
MATERIALS = (
    ('MA-7075', 'Кутник сталевий 40×40×4, 2 м', 'шт.', 'METAL', '520.00', '100', 15, True),
    ('MB-2024', 'Труба профільна 40×20×1,5, 2 м', 'шт.', 'METAL', '310.00', '100', 15, True),
    ('MB-6061', 'Труба профільна 30×30×1,5, 2 м', 'шт.', 'METAL', '295.00', '100', 15, True),
    ('MP-2503', 'Плита сталева 1200×600×3 мм', 'шт.', 'METAL', '1450.00', '20', 15, True),
    ('MT-1000', 'Лист рифлений 1500×700×3 мм', 'шт.', 'METAL', '1980.00', '20', 15, True),
    ('MS-6061', 'Лист сталевий 1250×2500×0,8 мм', 'шт.', 'METAL', '1380.00', '50', 15, True),
    ('MS-0253', 'Лист сталевий 1250×2500×1,0 мм', 'шт.', 'METAL', '1690.00', '50', 15, True),
    ('CB-2903', 'Болт М8×20 оцинкований', 'шт.', 'FAST', '3.40', '2000', 17, False),
    ('PB-6109', 'Болт М10×30 оцинкований', 'шт.', 'FAST', '5.20', '1000', 17, False),
    ('HN-4402', 'Гайка шестигранна М8', 'шт.', 'FAST', '1.80', '2000', 15, False),
    ('HN-5400', 'Гайка шестигранна М10', 'шт.', 'FAST', '2.60', '1000', 15, False),
    ('LW-4000', 'Шайба пружинна М8', 'шт.', 'FAST', '0.90', '2000', 18, False),
    ('FW-1000', 'Шайба плоска М10', 'шт.', 'FAST', '1.10', '1000', 15, False),
    ('LR-2398', 'Замок меблевий для шафи', 'шт.', 'FAST', '145.00', '50', 17, False),
    ('PA-187B', 'Фарба порошкова чорна RAL 9005', 'кг', 'PAINT', '265.00', '40', 16, False),
    ('PA-529S', 'Фарба порошкова сіра RAL 7035', 'кг', 'PAINT', '280.00', '40', 16, False),
)

# AdventureWorks Location rows 10, 20, 30, 40, 60 -> production route
ROUTE = (
    ('Формування каркаса', 'Розкрій і гнуття профілю за кресленням', 1),
    ('Зварювання', 'Зварити каркас, перевірити геометрію', 1),
    ('Зачищення', 'Зачистити шви й поверхні перед фарбуванням', 1),
    ('Фарбування', 'Порошкове фарбування й полімеризація', 1),
    ('Складання', 'Складання, комплектація кріплення, пакування', 1),
)

# code, name, planned cost UAH, sale price UAH, BOM {article: quantity per unit}
PRODUCTS = (
    ('SM-1800', 'Стелаж складський СМ-1800, 5 полиць', '4100.00', '6450.00',
     {'MA-7075': '4', 'MS-6061': '1', 'CB-2903': '40', 'HN-4402': '40', 'LW-4000': '40', 'PA-187B': '1.2'}),
    ('SM-2000', 'Стелаж складський СМ-2000 посилений', '5900.00', '8900.00',
     {'MA-7075': '4', 'MS-0253': '2', 'CB-2903': '48', 'HN-4402': '48', 'LW-4000': '48', 'PA-187B': '1.5'}),
    ('SV-1200', 'Стіл виробничий СВ-1200', '4100.00', '6900.00',
     {'MB-2024': '4', 'MP-2503': '1', 'MA-7075': '2', 'PB-6109': '16', 'HN-5400': '16', 'FW-1000': '16', 'PA-529S': '0.8'}),
    ('SV-1500', 'Стіл виробничий СВ-1500', '4700.00', '7800.00',
     {'MB-2024': '4', 'MT-1000': '1', 'MA-7075': '2', 'PB-6109': '16', 'HN-5400': '16', 'FW-1000': '16', 'PA-529S': '1'}),
    ('SHM-1', 'Шафа металева ШМ-1, одностулкова', '4200.00', '6990.00',
     {'MS-6061': '2', 'MB-6061': '2', 'LR-2398': '1', 'CB-2903': '24', 'HN-4402': '24', 'LW-4000': '24', 'PA-529S': '2'}),
    ('SHM-2', 'Шафа металева ШМ-2, двостулкова', '6850.00', '10900.00',
     {'MS-0253': '3', 'MB-6061': '2', 'LR-2398': '1', 'CB-2903': '32', 'HN-4402': '32', 'LW-4000': '32', 'PA-529S': '3'}),
    ('VS-1500', 'Верстак слюсарний ВС-1500', '5800.00', '9400.00',
     {'MT-1000': '1', 'MB-6061': '4', 'MA-7075': '4', 'PB-6109': '24', 'HN-5400': '24', 'FW-1000': '24', 'PA-529S': '1.2'}),
    ('TI-1', 'Тумба інструментальна ТІ-1, 5 шухляд', '4100.00', '6600.00',
     {'MS-6061': '2', 'MB-2024': '2', 'LR-2398': '1', 'CB-2903': '30', 'HN-4402': '30', 'LW-4000': '30', 'PA-187B': '1.5'}),
)

PRODUCT_NAMES = {code: name for code, name, *_ in PRODUCTS}
