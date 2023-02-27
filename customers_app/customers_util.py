from administration_app.utils import get_jsons_data_filter


def get_database_user_profile(ref_key):
    """
    Получение полиса ОМС из Регистра сведений
    :return: Найденную запись, или пустую строку
    """
    context = ""
    item = get_jsons_data_filter("InformationRegister", "ПолисыОМСФизическихЛиц", "ФизическоеЛицо_Key", ref_key, 0, 0)
    for record in item['value']:
        context = record['НомерПолиса']
    return context