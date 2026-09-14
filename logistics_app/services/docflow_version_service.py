"""Сервис версионирования файлов и защиты от изменений подсистемы СЭД (logistics_app)."""

import hashlib
import logging
from typing import Any, Optional

from django.db import transaction
from django.utils import timezone

from customers_app.models import DataBaseUser
from logistics_app.models import (
    DocFlowApprovalLog,
    DocFlowFile,
    DocFlowFileVersion,
)

logger = logging.getLogger(__name__)


class DocFlowVersionService:
    """Сервис управления версиями файлов электронного документооборота.

    Обеспечивает неизменяемость ранее загруженных версий, вычисление контрольных сумм SHA-256,
    автоматический инкремент номеров версий (мажорный/минорный) и протоколирование
    в неизменяемом журнале аудита DocFlowApprovalLog.
    """

    @classmethod
    def calculate_file_hash_and_size(cls, file_obj: Any) -> tuple[str, int]:
        """Вычисляет контрольную сумму SHA-256 и размер переданного файла.

        Args:
            file_obj (Any): Файловый объект (UploadedFile / FieldFile).

        Returns:
            tuple[str, int]: Кортеж (sha256_hex_hash, file_size_in_bytes).
        """
        sha256 = hashlib.sha256()
        file_size = 0

        # Сохраняем исходную позицию курсора, если поддерживается
        if hasattr(file_obj, "seek") and callable(file_obj.seek):
            file_obj.seek(0)

        if hasattr(file_obj, "chunks"):
            for chunk in file_obj.chunks():
                sha256.update(chunk)
                file_size += len(chunk)
        else:
            data = file_obj.read()
            sha256.update(data)
            file_size = len(data)

        if hasattr(file_obj, "seek") and callable(file_obj.seek):
            file_obj.seek(0)

        return sha256.hexdigest(), file_size

    @classmethod
    def calculate_next_version_number(
        cls,
        current_version: str,
        is_reviewer_edit: bool = False,
    ) -> str:
        """Вычисляет следующий номер версии файла на основе текущего номера и типа правки.

        При редакционных правках согласующего (is_reviewer_edit=True) инкрементируется
        минорная версия (например, '1.0' -> '1.1', '1.1' -> '1.2').
        При загрузке новой редакции автором на доработке инкрементируется
        мажорная версия (например, '1.0' -> '2.0', '1.3' -> '2.0').

        Args:
            current_version (str): Текущий номер версии (например, '1.0').
            is_reviewer_edit (bool): Флаг правки согласующим лицом. Defaults to False.

        Returns:
            str: Следующий строковый номер версии (например, '1.1' или '2.0').
        """
        if not current_version:
            return "1.0"

        try:
            parts = current_version.strip().split(".")
            major = int(parts[0])
            minor = int(parts[1]) if len(parts) > 1 else 0

            if is_reviewer_edit:
                return f"{major}.{minor + 1}"
            else:
                return f"{major + 1}.0"
        except (ValueError, IndexError):
            return f"{current_version}.1"

    @classmethod
    def upload_new_file_version(
        cls,
        doc_file: DocFlowFile,
        file_obj: Any,
        user: DataBaseUser,
        comment: str = "",
        is_reviewer_edit: bool = False,
        version_number: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: str = "",
    ) -> DocFlowFileVersion:
        """Сохраняет новую физическую версию файла документа СЭД с аудитом.

        Вычисляет SHA-256 хэш, размер, определяет инкремент версии, обновляет контейнер
        DocFlowFile и создает запись в журнале аудита DocFlowApprovalLog.

        Args:
            doc_file (DocFlowFile): Контейнер файла документа.
            file_obj (Any): Загружаемый физический файл.
            user (DataBaseUser): Пользователь, загрузивший версию.
            comment (str): Пояснение автора или согласующего к изменениям. Defaults to "".
            is_reviewer_edit (bool): Признак загрузки версии согласующим. Defaults to False.
            version_number (Optional[str]): Принудительно заданный номер версии. Defaults to None.
            ip_address (Optional[str]): IP-адрес клиентского устройства. Defaults to None.
            user_agent (str): User-Agent браузера пользователя. Defaults to "".

        Returns:
            DocFlowFileVersion: Созданный экземпляр версии файла.

        Raises:
            ValueError: Если не передан файл или отсутствуют необходимые данные.
        """
        if not file_obj:
            raise ValueError("Файл для загрузки новой версии не может быть пустым.")

        document = doc_file.document
        if document and document.is_finalized:
            raise ValueError(
                f"Документ {document.reg_number or document.id} находится в завершенном статусе "
                f"«{document.get_status_display()}» и защищен от изменения файлов и загрузки новых версий."
            )

        file_hash, file_size = cls.calculate_file_hash_and_size(file_obj)

        if not version_number:
            version_number = cls.calculate_next_version_number(
                current_version=doc_file.current_version_number,
                is_reviewer_edit=is_reviewer_edit,
            )

        with transaction.atomic():
            # Блокируем родительский контейнер файла
            doc_file_locked = DocFlowFile.objects.select_for_update().get(id=doc_file.id)

            file_version = DocFlowFileVersion.objects.create(
                doc_file=doc_file_locked,
                version_number=version_number,
                file=file_obj,
                file_size=file_size,
                file_hash=file_hash,
                uploaded_by=user,
                change_comment=comment,
                is_reviewer_edit=is_reviewer_edit,
            )

            # Обновляем текущую версию в контейнере файла
            doc_file_locked.current_version_number = version_number
            doc_file_locked.save(update_fields=["current_version_number"])

            # Фиксируем загрузку в неизменяемом журнале аудита
            action_desc = "Согласующим лицом загружена редакция с правками" if is_reviewer_edit else "Загружена новая версия файла"
            log_comment = f"{action_desc} v{version_number} к файлу «{doc_file.title}». {comment}".strip()

            DocFlowApprovalLog.objects.create(
                document=doc_file.document,
                user=user,
                action=DocFlowApprovalLog.Action.NEW_VERSION_UPLOADED,
                comment=log_comment,
                ip_address=ip_address,
                user_agent=user_agent[:500] if user_agent else "",
            )

            logger.info(
                "Документ UUID %s: загружена версия файла %s v%s пользователем %s",
                doc_file.document_id,
                doc_file.title,
                version_number,
                user,
            )

            return file_version
