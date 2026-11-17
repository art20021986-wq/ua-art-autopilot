"""Public holidays of the Republic of Korea (관공서의 공휴일, with substitute holidays and election days) for the Korea
page day buttons (KOREA-HOLIDAYS-001). One table, updated once a year from an official list; Korea dates 'YYYY/MM/DD',
names (uk, ru, ka).

Checked 2026-11-17: for the rest of 2026 only Christmas (성탄절, 25 December — a fixed public holiday under
관공서의 공휴일에 관한 규정, art. 2). 2027 is added at the yearly update from the official list (KASI 월력요항 /
VISITKOREA): the official pages could not be read from the build environment on 2026-11-17, so no 2027 date is
entered — nothing from memory. Until then a 2027 holiday on a weekday shows «0 авто», on a weekend «Вихідний».
"""
HOLIDAYS = {
    '2026/12/25': ('Різдво', 'Рождество', 'შობა'),
}
UPDATED = '2026-11-17'
