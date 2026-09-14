from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import RecommendationRequestSerializer
from .service import recommend


class RecommendationView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RecommendationRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'success': False, 'data': None, 'message': serializer.errors}, status=400)
        data, message = recommend(serializer.validated_data, request.user)
        return Response({'success': True, 'data': data, 'message': message})
