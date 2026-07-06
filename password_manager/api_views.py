from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from .models import EncryptedPassword
from .services import PasswordService

class PasswordListAPIView(APIView):
    """
    API endpoint that allows passwords to be viewed or created.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        passwords = EncryptedPassword.objects.filter(owner=request.user)
        data = []
        for p in passwords:
            decrypted = p.encrypted_password
            if p.admin_encrypted_copy:
                try:
                    decrypted = PasswordService.admin_decrypt(p.admin_encrypted_copy)
                except Exception:
                    decrypted = "[Ошибка дешифровки]"
            
            data.append({
                "id": p.id,
                "service": p.title or p.url or p.get_resource_type_display(),
                "username": p.login,
                "encrypted_password": decrypted,
                "notes": p.notes
            })
        return Response(data)

    def post(self, request):
        data = request.data
        plaintext = data.get('encrypted_password', '')
        
        try:
            admin_enc = PasswordService.encrypt_for_admin(plaintext)
        except Exception:
            admin_enc = plaintext  # Fallback если ключ не настроен

        p = EncryptedPassword.objects.create(
            owner=request.user,
            title=data.get('service', ''),
            login=data.get('username', ''),
            encrypted_password=admin_enc, # Сохраняем зашифрованную версию
            admin_encrypted_copy=admin_enc,
            notes=data.get('notes', ''),
            url='',
            resource_type='website'
        )
        
        return Response({
            "id": p.id,
            "service": p.title,
            "username": p.login,
            "encrypted_password": plaintext, # Возвращаем plain text при создании
            "notes": p.notes
        }, status=status.HTTP_201_CREATED)
