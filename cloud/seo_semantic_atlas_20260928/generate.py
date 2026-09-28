#!/usr/bin/env python3
"""Generate a large RU/UA/KA SEO demand atlas. Research data only; never publishes pages."""
import csv, itertools, pathlib
MODELS=["Kia K5","Hyundai Sonata","Hyundai Tucson","Kia Sportage","Hyundai Santa Fe","Kia Carnival","Kia K7","Kia K8","Hyundai Grandeur","Hyundai Avante","Hyundai Elantra","Hyundai Staria","Genesis G70","Genesis G80","Genesis G90","Renault Korea QM6","Renault Korea SM6","Nissan Note","Toyota Aqua","Toyota Prius","Tesla Model Y","Tesla Model 3","Ford Escape","Nissan Rogue","BMW X3","Volkswagen Golf","Volkswagen Tiguan","Audi Q5","Skoda Octavia","Renault Megane","BYD Song Plus","Volkswagen ID.4","BYD Yuan Plus","Zeekr 001","BYD Seal","Mercedes-Benz B-Class","Audi A6"]
LANG={
"ru":{"geo":["Киев","Украина","Грузия","Тбилиси","Рустави","Батуми","Кутаиси","Поти"],"base":["авто из Кореи","машины из Кореи","автомобиль из Кореи","корейские авто"],"intent":["купить","цена","стоимость","под ключ","доставка","доставка из Кореи","растаможка","таможня","аукцион","Encar","проверка","диагностика","пробег","отзывы","в наличии","на заказ","LPG","LPi","заводской газ","расход газа","комплектация","VIN","цена с доставкой","цена под ключ","срок доставки","как заказать","как купить","выгодно ли","что выбрать","сравнение"]},
"uk":{"geo":["Київ","Україна","Грузія","Тбілісі","Руставі","Батумі","Кутаїсі","Поті"],"base":["авто з Кореї","машини з Кореї","автомобіль з Кореї","корейські авто"],"intent":["купити","ціна","вартість","під ключ","доставка","доставка з Кореї","розмитнення","митниця","аукціон","Encar","перевірка","діагностика","пробіг","відгуки","в наявності","під замовлення","LPG","LPi","заводський газ","витрата газу","комплектація","VIN","ціна з доставкою","ціна під ключ","термін доставки","як замовити","як купити","чи вигідно","що обрати","порівняння"]},
"ka":{"geo":["საქართველო","თბილისი","რუსთავი","ბათუმი","ქუთაისი","ფოთი"],"base":["ავტომობილი კორეიდან","მანქანა კორეიდან","კორეული ავტომობილები","კორეული მანქანები"],"intent":["ყიდვა","ფასი","ღირებულება","სრული მომსახურებით","ჩამოყვანა","კორეიდან ჩამოყვანა","განბაჟება","საბაჟო","აუქციონი","Encar","შემოწმება","დიაგნოსტიკა","გარბენი","მიმოხილვა","იყიდება","შეკვეთით","LPG","LPi","ქარხნული გაზი","გაზის ხარჯი","კომპლექტაცია","VIN","მიწოდების ფასი","სრული ფასი","ჩამოყვანის ვადა","როგორ შევუკვეთო","როგორ ვიყიდო","ღირს თუ არა","რომელი ავირჩიო","შედარება"]}
}
YEARS=[str(y) for y in range(2016,2027)]
FUELS={"ru":["LPG","LPi","газ","гибрид","бензин","дизель","электро"],"uk":["LPG","LPi","газ","гібрид","бензин","дизель","електро"],"ka":["LPG","LPi","გაზი","ჰიბრიდი","ბენზინი","დიზელი","ელექტრო"]}
def clean(s):return " ".join(s.split())
rows=set()
for lang,d in LANG.items():
 for base,intent,geo in itertools.product(d["base"],d["intent"],d["geo"]):
  rows.add((lang,"category",clean(f"{base} {intent} {geo}")))
 for model,intent,geo in itertools.product(MODELS,d["intent"],d["geo"]):
  rows.add((lang,"model_intent",clean(f"{model} {intent} {geo}")))
 for model,fuel,geo in itertools.product(MODELS,FUELS[lang],d["geo"]):
  rows.add((lang,"model_fuel",clean(f"{model} {fuel} {geo}")))
 for model,year,geo in itertools.product(MODELS,YEARS,d["geo"]):
  rows.add((lang,"model_year",clean(f"{model} {year} {geo}")))
 for model,year,fuel,geo in itertools.product(MODELS,YEARS,FUELS[lang],d["geo"]):
  rows.add((lang,"model_year_fuel",clean(f"{model} {year} {fuel} {geo}")))
 for model in MODELS:
  for other in MODELS:
   if model<other: rows.add((lang,"comparison",clean(f"{model} vs {other}")))
out=pathlib.Path("cloud/seo_semantic_atlas_20260928/semantic_atlas.csv");out.parent.mkdir(parents=True,exist_ok=True)
with out.open("w",encoding="utf-8",newline="") as f:
 w=csv.writer(f);w.writerow(["language","cluster","query"]);w.writerows(sorted(rows))
print("SEMANTIC_ATLAS_ROWS",len(rows))
print("NOTE: candidate demand map, not claimed search-volume data; do not create one page per query.")
