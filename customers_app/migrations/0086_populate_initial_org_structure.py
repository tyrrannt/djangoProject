# Data Migration for Initial Company Org Structure (ООО Авиакомпания БАРКОЛ с 03.09.2026)

import datetime
from django.db import migrations


def populate_org_structure(apps, schema_editor):
    OrgStructure = apps.get_model("customers_app", "OrgStructure")
    OrgStructureNode = apps.get_model("customers_app", "OrgStructureNode")
    Division = apps.get_model("customers_app", "Division")
    Job = apps.get_model("customers_app", "Job")

    # Helper to find Division by name prefix/substring
    def find_division(name):
        return Division.objects.filter(name__icontains=name).first()

    # Helper to find Job by name prefix/substring
    def find_job(name):
        return Job.objects.filter(name__icontains=name).first()

    # 1. Create or get primary OrgStructure
    structure, _ = OrgStructure.objects.get_or_create(
        version_code="2026-09",
        defaults={
            "title": "Общая структурная схема ООО Авиакомпания «БАРКОЛ»",
            "start_date": datetime.date(2026, 9, 3),
            "is_active": True,
            "approved_by": "Генеральный директор В.С. Бархотов",
            "approval_date": datetime.date(2026, 9, 3),
            "description": "Утверждено Генеральным директором ООО «Авиакомпания «БАРКОЛ» В.С. Бархотовым от 03.09.2026 г. Согласовано: Начальник отдела кадров И.А. Кирюшкина.",
        },
    )

    if structure.nodes.exists():
        return

    # Root: Генеральный директор
    root_job = find_job("Генеральный директор")
    root_div = find_division("Руководство") or find_division("Администрация") or find_division("Генеральный")
    root_node = OrgStructureNode.objects.create(
        structure=structure,
        custom_name="Генеральный директор",
        division=root_div,
        head_job=root_job,
        node_type="TOP_MANAGEMENT",
        level=0,
        order=0,
        pos_x=580,
        pos_y=50,
        color_scheme="dark",
    )

    # Advisory & Assistants to Root
    OrgStructureNode.objects.create(
        structure=structure,
        custom_name="Совет по безопасности полетов",
        parent=root_node,
        node_type="ADVISORY",
        level=1,
        order=90,
        pos_x=850,
        pos_y=35,
        color_scheme="gray",
    )
    OrgStructureNode.objects.create(
        structure=structure,
        custom_name="Помощник генерального директора",
        parent=root_node,
        head_job=find_job("Помощник"),
        node_type="ASSISTANT",
        level=1,
        order=91,
        pos_x=850,
        pos_y=135,
        color_scheme="gray",
    )
    OrgStructureNode.objects.create(
        structure=structure,
        custom_name="Секретарь-делопроизводитель",
        parent=root_node,
        division=find_division("Секретариат") or find_division("Канцелярия"),
        head_job=find_job("Секретарь") or find_job("Делопроизводитель"),
        node_type="ASSISTANT",
        level=1,
        order=92,
        pos_x=310,
        pos_y=50,
        color_scheme="gray",
    )

    # 1. Первый заместитель генерального директора - исполнительный директор (Колонка 0: x = 40)
    exec_div = find_division("Исполнительный")
    exec_job = find_job("Первый заместитель генерального директора") or find_job("Исполнительный директор")
    exec_node = OrgStructureNode.objects.create(
        structure=structure,
        custom_name="Первый заместитель генерального директора - исполнительный директор",
        division=exec_div,
        head_job=exec_job,
        parent=root_node,
        node_type="TOP_MANAGEMENT",
        level=1,
        order=1,
        pos_x=40,
        pos_y=240,
        color_scheme="blue",
    )

    exec_children = [
        ("Заместитель исполнительного директора", "Заместитель исполнительного", "DIVISION", "blue"),
        ("Отдел организации перевозок и авиационных работ", "организации перевозок", "DIVISION", "blue"),
        ("Производственно-диспетчерский отдел (организация полетов)", "Производственно-диспетчерский отдел (организация полетов)", "DIVISION", "blue"),
        ("Отдел организации наземного обслуживания", "наземного обслуживания", "DIVISION", "blue"),
        ("Служба горюче-смазочных материалов и наземного транспорта", "ГСМ", "SERVICE", "blue"),
        ("Транспортная группа", "Транспортная", "GROUP", "blue"),
        ("Группа представители АК на МПД", "представители АК на МПД", "GROUP", "blue"),
        ("Специалист - эксперт по тендерной работе", "тендерной работе", "GROUP", "blue"),
    ]
    for idx, (name, search_key, ntype, color) in enumerate(exec_children):
        OrgStructureNode.objects.create(
            structure=structure,
            custom_name=name,
            division=find_division(search_key) or find_division(name),
            head_job=find_job(name) or find_job(search_key),
            parent=exec_node,
            node_type=ntype,
            level=2,
            order=idx,
            pos_x=40,
            pos_y=365 + idx * 125,
            color_scheme=color,
        )

    # 2. Летная служба (Колонка 1: x = 310)
    flight_dir_job = find_job("Заместитель генерального директора по организации летной работы") or find_job("Летный директор")
    flight_node = OrgStructureNode.objects.create(
        structure=structure,
        custom_name="Заместитель генерального директора по организации летной работы - летный директор (Летная служба)",
        division=find_division("Летная служба") or find_division("Летный"),
        head_job=flight_dir_job,
        parent=root_node,
        node_type="SERVICE",
        level=1,
        order=2,
        pos_x=310,
        pos_y=240,
        color_scheme="indigo",
    )
    OrgStructureNode.objects.create(
        structure=structure,
        custom_name="Авиационный учебный центр «БАРКОЛ»",
        division=find_division("АУЦ") or find_division("Авиационный учебный центр"),
        parent=flight_node,
        node_type="DIVISION",
        level=2,
        order=1,
        pos_x=310,
        pos_y=365,
        color_scheme="indigo",
    )
    OrgStructureNode.objects.create(
        structure=structure,
        custom_name="Отдел планирования",
        division=find_division("планирования"),
        parent=flight_node,
        node_type="DIVISION",
        level=2,
        order=2,
        pos_x=310,
        pos_y=490,
        color_scheme="indigo",
    )
    flight_squad = OrgStructureNode.objects.create(
        structure=structure,
        custom_name="Летный отряд",
        division=find_division("Летный отряд"),
        head_job=find_job("командир летного отряда") or find_job("Заместитель летного директора"),
        parent=flight_node,
        node_type="DETACHMENT",
        level=2,
        order=3,
        pos_x=310,
        pos_y=615,
        color_scheme="amber",
    )
    flight_squad_items = [
        ("Штаб летного отряда", "Штаб", "GROUP", "amber"),
        ("Врач летного отряда", "Врач", "GROUP", "amber"),
        ("Заместитель командира летного отряда", "Заместитель командира", "GROUP", "amber"),
        ("Авиационные специалисты (Ми-8, R44, R66)", "Авиационные специалисты", "GROUP", "amber"),
    ]
    for idx, (sname, skey, stype, scolor) in enumerate(flight_squad_items):
        OrgStructureNode.objects.create(
            structure=structure,
            custom_name=sname,
            division=find_division(skey) or find_division(sname),
            head_job=find_job(sname) or find_job(skey),
            parent=flight_squad,
            node_type=stype,
            level=3,
            order=idx,
            pos_x=310,
            pos_y=740 + idx * 125,
            color_scheme=scolor,
        )

    # 3. Инженерно-авиационная служба (ИАС) (Колонка 2: x = 580)
    ias_job = find_job("Заместитель генерального директора по инженерно-авиационной службе") or find_job("Технический директор")
    ias_node = OrgStructureNode.objects.create(
        structure=structure,
        custom_name="Заместитель генерального директора по инженерно-авиационной службе - технический директор (ИАС)",
        division=find_division("ИАС") or find_division("Инженерно-авиационная служба"),
        head_job=ias_job,
        parent=root_node,
        node_type="SERVICE",
        level=1,
        order=3,
        pos_x=580,
        pos_y=240,
        color_scheme="cyan",
    )
    ias_items = [
        ("Заместитель технического директора", "Заместитель технического", "GROUP", "cyan"),
        ("Группа контроля качества", "контроля качества", "GROUP", "cyan"),
        ("Секретарь-делопроизводитель ИАС", "Секретарь-делопроизводитель", "GROUP", "cyan"),
        ("Производственный отдел", "Производственный отдел", "DIVISION", "cyan"),
        ("Ведущий специалист", "Ведущий специалист", "GROUP", "cyan"),
        ("Производственно-диспетчерский отдел ИАС", "Производственно-диспетчерский отдел", "DIVISION", "cyan"),
        ("Отдел авиационно-технического обеспечения и ремонта авиационной техники", "авиационно-технического обеспечения", "DIVISION", "cyan"),
        ("Участок технического обслуживания", "Участок технического обслуживания", "GROUP", "cyan"),
    ]
    for idx, (iname, ikey, itype, icolor) in enumerate(ias_items):
        OrgStructureNode.objects.create(
            structure=structure,
            custom_name=iname,
            division=find_division(ikey) or find_division(iname),
            head_job=find_job(iname) or find_job(ikey),
            parent=ias_node,
            node_type=itype,
            level=2,
            order=idx,
            pos_x=580,
            pos_y=365 + idx * 125,
            color_scheme=icolor,
        )

    # 4. Заместитель генерального директора по безопасности полетов и качеству & Кадры/Юротдел (Колонка 3: x = 850)
    bp_job = find_job("по безопасности полетов и качеству") or find_job("безопасности полетов")
    bp_node = OrgStructureNode.objects.create(
        structure=structure,
        custom_name="Заместитель генерального директора по безопасности полетов и качеству",
        division=find_division("безопасности полетов"),
        head_job=bp_job,
        parent=root_node,
        node_type="TOP_MANAGEMENT",
        level=1,
        order=4,
        pos_x=850,
        pos_y=240,
        color_scheme="teal",
    )
    bp_items = [
        ("Пилот-инспектор по безопасности полетов", "Пилот-инспектор", "GROUP", "teal"),
        ("Отдел качества и сертификации", "Отдел качества", "DIVISION", "teal"),
        ("Группа расшифровки и анализа полетной информации", "расшифровки и анализа", "GROUP", "teal"),
    ]
    for idx, (bname, bkey, btype, bcolor) in enumerate(bp_items):
        OrgStructureNode.objects.create(
            structure=structure,
            custom_name=bname,
            division=find_division(bkey) or find_division(bname),
            head_job=find_job(bname) or find_job(bkey),
            parent=bp_node,
            node_type=btype,
            level=2,
            order=idx,
            pos_x=850,
            pos_y=365 + idx * 125,
            color_scheme=bcolor,
        )

    hr_legal_node = OrgStructureNode.objects.create(
        structure=structure,
        custom_name="Заместитель генерального директора (Кадры, охрана труда, ИАО, Юр. отдел)",
        parent=root_node,
        node_type="TOP_MANAGEMENT",
        level=1,
        order=8,
        pos_x=850,
        pos_y=755,
        color_scheme="red",
    )
    hr_legal_items = [
        ("Отдел кадров", "кадр", "DIVISION", "red"),
        ("Отдел охраны труда и пожарной безопасности", "охраны труда", "DIVISION", "red"),
        ("Информационно-аналитический отдел", "Информационно-аналитический", "DIVISION", "red"),
        ("Юридический отдел", "Юридический", "DIVISION", "red"),
    ]
    for idx, (hname, hkey, htype, hcolor) in enumerate(hr_legal_items):
        OrgStructureNode.objects.create(
            structure=structure,
            custom_name=hname,
            division=find_division(hkey) or find_division(hname),
            head_job=find_job(hname) or find_job(hkey),
            parent=hr_legal_node,
            node_type=htype,
            level=2,
            order=idx,
            pos_x=850,
            pos_y=880 + idx * 125,
            color_scheme=hcolor,
        )

    # 5. Главный бухгалтер, ТБ, Склад (Колонка 4: x = 1120)
    buh_job = find_job("Главный бухгалтер")
    buh_node = OrgStructureNode.objects.create(
        structure=structure,
        custom_name="Главный бухгалтер",
        division=find_division("Бухгалтерия"),
        head_job=buh_job,
        parent=root_node,
        node_type="TOP_MANAGEMENT",
        level=1,
        order=5,
        pos_x=1120,
        pos_y=240,
        color_scheme="purple",
    )
    OrgStructureNode.objects.create(
        structure=structure,
        custom_name="Бухгалтерия",
        division=find_division("Бухгалтерия"),
        parent=buh_node,
        node_type="DIVISION",
        level=2,
        order=1,
        pos_x=1120,
        pos_y=365,
        color_scheme="purple",
    )

    tb_job = find_job("транспортной безопасности")
    tb_node = OrgStructureNode.objects.create(
        structure=structure,
        custom_name="Заместитель генерального директора по транспортной безопасности",
        division=find_division("транспортной безопасности"),
        head_job=tb_job,
        parent=root_node,
        node_type="TOP_MANAGEMENT",
        level=1,
        order=7,
        pos_x=1120,
        pos_y=505,
        color_scheme="orange",
    )
    tb_items = [
        ("Инспектор по транспортной безопасности", "Инспектор по транспортной", "GROUP", "orange"),
        ("Специалисты мониторинга и контроля", "Специалисты мониторинга", "GROUP", "orange"),
    ]
    for idx, (tname, tkey, ttype, tcolor) in enumerate(tb_items):
        OrgStructureNode.objects.create(
            structure=structure,
            custom_name=tname,
            division=find_division(tkey) or find_division(tname),
            head_job=find_job(tname) or find_job(tkey),
            parent=tb_node,
            node_type=ttype,
            level=2,
            order=idx,
            pos_x=1120,
            pos_y=630 + idx * 125,
            color_scheme=tcolor,
        )

    sklad_node = OrgStructureNode.objects.create(
        structure=structure,
        custom_name="Заместитель генерального директора (Складской комплекс)",
        division=find_division("Склад"),
        parent=root_node,
        node_type="TOP_MANAGEMENT",
        level=1,
        order=6,
        pos_x=1120,
        pos_y=895,
        color_scheme="lime",
    )
    OrgStructureNode.objects.create(
        structure=structure,
        custom_name="Склад",
        division=find_division("Склад"),
        parent=sklad_node,
        node_type="DIVISION",
        level=2,
        order=1,
        pos_x=1120,
        pos_y=1020,
        color_scheme="lime",
    )

    # ОП МПД (Обособленные подразделения) в 2 ряда по 6 колонок
    op_mpd_list = [
        "ОП МПД «Аэропорт Брянск»", "ОП МПД «Мячково»", "ОП МПД «Лопатино»",
        "ОП МПД «Аэропорт Протасово»", "ОП МПД «Аэропорт Туношна»", "ОП МПД «Переслегино»",
        "ОП МПД «Невская»", "ОП МПД «Аэропорт Волгоград»", "ОП МПД «Песь»",
        "ОП МПД «Мурманск»", "ОП МПД «Оренбург»", "ОП «Нягань»"
    ]
    for idx, op_name in enumerate(op_mpd_list):
        cleaned = op_name.replace("ОП МПД", "").replace("ОП", "").replace("«", "").replace("»", "").strip()
        col = idx % 6
        row = idx // 6
        OrgStructureNode.objects.create(
            structure=structure,
            custom_name=op_name,
            division=find_division(cleaned) or find_division(op_name),
            parent=exec_node,
            node_type="SUBDIVISION",
            level=3,
            order=50 + idx,
            pos_x=40 + col * 220,
            pos_y=1390 + row * 115,
            color_scheme="green",
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("customers_app", "0085_orgstructure_orgstructurenode_orgnodeleadershiphistory"),
    ]

    operations = [
        migrations.RunPython(populate_org_structure, reverse_code=noop),
    ]
