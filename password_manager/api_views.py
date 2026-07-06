from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from .models import EncryptedPassword

class PasswordListAPIView(APIView):
    """
    API endpoint that allows passwords to be viewed or created.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        passwords = EncryptedPassword.objects.filter(owner=request.user)
        data = []
        for p in passwords:
            data.append({
                "id": p.id,
                "service": p.title or p.url or p.get_resource_type_display(),
                "username": p.login,
                "encrypted_password": p.encrypted_password,
                "notes": p.notes
            })
        return Response(data)

    def post(self, request):
        data = request.data
        p = EncryptedPassword.objects.create(
            owner=request.user,
            title=data.get('service', ''),
            login=data.get('username', ''),
            encrypted_password=data.get('encrypted_password', ''),
            notes=data.get('notes', ''),
            url='',
            resource_type='website'
        )
        return Response({
            "id": p.id,
            "service": p.title,
            "username": p.login,
            "encrypted_password": p.encrypted_password,
            "notes": p.notes
        }, status=status.HTTP_201_CREATED)
