from django.db import transaction
from django.db.models import Avg, F, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.views import APIView
from .models import (User, Review, ReviewLike, PointEntry, Companion, CompanionMember,
                     RecentPlace, Plan, Inquiry)
from .activity_serializers import (ProfileSerializer, ReviewSerializer, CompanionSerializer,
                                   PlanSerializer, InquirySerializer)
from .serializers import FavoriteCreateSerializer
from .views import success_response, error_response
from places.models import Place


def review_data(item, request):
    return {'id': item.id, 'place_id': item.place_id, 'place_name': item.place.name,
            'author_id': item.user_id, 'author_nickname': item.user.nickname,
            'text': item.text, 'rating': item.rating,
            'photo_url': request.build_absolute_uri(item.photo.url) if item.photo else None,
            'created_at': item.created_at, 'like_count': item.likes.count(),
            'is_liked': request.user.is_authenticated and item.likes.filter(user=request.user).exists(),
            'is_mine': request.user.id == item.user_id, 'visit_verified': False}


def companion_data(item, request):
    return {'id': item.id, 'place_id': item.place_id, 'place_name': item.place.name,
            'place_address': item.place.address,
            'author_id': item.user_id, 'author_nickname': item.user.nickname,
            'title': item.title, 'text': item.text, 'date': item.date,
            'capacity': item.capacity, 'member_count': item.member_count,
            'is_joined': request.user.is_authenticated and item.members.filter(user=request.user).exists(),
            'is_mine': request.user.id == item.user_id, 'created_at': item.created_at}


def update_rating(place):
    Place.objects.filter(pk=place.pk).update(avg_rating=Review.objects.filter(place=place).aggregate(value=Avg('rating'))['value'])


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return success_response(ProfileSerializer(request.user).data)

    def patch(self, request):
        serializer = ProfileSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return success_response(serializer.data)


class ReviewsView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get(self, request):
        items = Review.objects.select_related('user', 'place').prefetch_related('likes').order_by('-created_at')
        if request.query_params.get('place_id'):
            place_id = serializers.IntegerField(min_value=1).run_validation(request.query_params['place_id'])
            items = items.filter(place_id=place_id)
        if request.query_params.get('mine') == 'true':
            items = items.filter(user_id=request.user.id) if request.user.is_authenticated else items.none()
        return success_response({'items': [review_data(item, request) for item in items]})

    @transaction.atomic
    def post(self, request):
        serializer = ReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Serialize a user's awards; DB uniqueness also prevents duplicate rewards after delete/recreate.
        User.objects.select_for_update().get(pk=request.user.pk)
        item = serializer.save(user=request.user)
        _, awarded = PointEntry.objects.get_or_create(user=request.user, place=item.place,
            reason='review_created', defaults={'amount': 50})
        update_rating(item.place)
        return success_response({'review': review_data(item, request), 'points_awarded': 50 if awarded else 0}, status_code=201)


class ReviewDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def patch(self, request, pk):
        item = get_object_or_404(Review, pk=pk, user=request.user)
        serializer = ReviewSerializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        if 'place' in serializer.validated_data and serializer.validated_data['place'] != item.place:
            return error_response('등록된 후기의 장소는 변경할 수 없습니다.')
        serializer.save()
        update_rating(item.place)
        return success_response(review_data(item, request))

    @transaction.atomic
    def delete(self, request, pk):
        item = get_object_or_404(Review, pk=pk, user=request.user)
        place = item.place
        item.delete()
        update_rating(place)
        return success_response()


class ReviewLikeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        item = get_object_or_404(Review, pk=pk)
        ReviewLike.objects.get_or_create(user=request.user, review=item)
        return success_response(review_data(item, request))

    def delete(self, request, pk):
        item = get_object_or_404(Review, pk=pk)
        ReviewLike.objects.filter(user=request.user, review=item).delete()
        return success_response(review_data(item, request))


class CompanionsView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get(self, request):
        items = Companion.objects.select_related('user', 'place').order_by('date', '-created_at')
        if request.query_params.get('date'):
            date = serializers.DateField().run_validation(request.query_params['date'])
            items = items.filter(date=date)
        if request.query_params.get('mine') == 'true':
            items = items.filter(members__user_id=request.user.id) if request.user.is_authenticated else items.none()
        return success_response({'items': [companion_data(item, request) for item in items]})

    @transaction.atomic
    def post(self, request):
        serializer = CompanionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = serializer.save(user=request.user)
        CompanionMember.objects.create(user=request.user, companion=item)
        return success_response(companion_data(item, request), status_code=201)


class CompanionDetailView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get(self, request, pk):
        return success_response(companion_data(get_object_or_404(Companion, pk=pk), request))

    @transaction.atomic
    def patch(self, request, pk):
        item = get_object_or_404(Companion.objects.select_for_update(), pk=pk, user=request.user)
        serializer = CompanionSerializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return success_response(companion_data(item, request))

    def delete(self, request, pk):
        get_object_or_404(Companion, pk=pk, user=request.user).delete()
        return success_response()


class CompanionJoinView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk):
        item = get_object_or_404(Companion.objects.select_for_update(), pk=pk)
        if item.date < timezone.localdate():
            return error_response('종료된 모집에는 참여할 수 없습니다.')
        if item.members.filter(user=request.user).exists():
            return success_response(companion_data(item, request))
        # Atomic conditional update enforces capacity even on databases without row locks.
        if not Companion.objects.filter(pk=pk, member_count__lt=F('capacity')).update(member_count=F('member_count') + 1):
            return error_response('모집 정원이 찼습니다.', 409)
        CompanionMember.objects.create(companion=item, user=request.user)
        item.refresh_from_db()
        return success_response(companion_data(item, request))

    @transaction.atomic
    def delete(self, request, pk):
        item = get_object_or_404(Companion.objects.select_for_update(), pk=pk)
        if item.user_id == request.user.id:
            return error_response('모집자는 나갈 수 없습니다. 모집 글을 삭제해 주세요.')
        deleted, _ = CompanionMember.objects.filter(companion=item, user=request.user).delete()
        if deleted:
            Companion.objects.filter(pk=pk).update(member_count=F('member_count') - 1)
        item.refresh_from_db()
        return success_response(companion_data(item, request))


class PointsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        items = PointEntry.objects.filter(user=request.user).order_by('-created_at')
        return success_response({'balance': items.aggregate(value=Sum('amount'))['value'] or 0,
            'items': list(items.values('id', 'amount', 'reason', 'created_at'))})


class RewardsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return success_response({'items': []}, '현재 교환 가능한 제휴 상품이 없습니다.')


class RecentPlacesView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        RecentPlace.objects.filter(user=request.user).delete()
        return success_response()

    def get(self, request):
        return success_response({'place_ids': list(RecentPlace.objects.filter(user=request.user).order_by('-viewed_at').values_list('place_id', flat=True)[:50])})

    def post(self, request):
        serializer = FavoriteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        RecentPlace.objects.update_or_create(user=request.user, place_id=serializer.validated_data['place_id'], defaults={'viewed_at': timezone.now()})
        return success_response(serializer.validated_data)


class PlansView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return success_response({'items': PlanSerializer(Plan.objects.filter(user=request.user).order_by('date'), many=True).data})

    def post(self, request):
        serializer = PlanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user)
        return success_response(serializer.data, status_code=201)


class PlanDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        get_object_or_404(Plan, pk=pk, user=request.user).delete()
        return success_response()


class InquiriesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return success_response({'items': InquirySerializer(Inquiry.objects.filter(user=request.user).order_by('-created_at'), many=True).data})

    def post(self, request):
        serializer = InquirySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user)
        return success_response(serializer.data, '문의가 저장되었습니다.', 201)


class NotificationsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        items = []
        for like in ReviewLike.objects.filter(review__user=request.user).exclude(user=request.user).select_related('user', 'review__place').order_by('-created_at')[:50]:
            items.append({'id': f'like-{like.pk}', 'title': '후기 좋아요', 'body': f'{like.user.nickname}님이 {like.review.place.name} 후기를 좋아합니다.', 'created_at': like.created_at})
        for member in CompanionMember.objects.filter(companion__user=request.user).exclude(user=request.user).select_related('user', 'companion').order_by('-created_at')[:50]:
            items.append({'id': f'join-{member.pk}', 'title': '동행 참여', 'body': f'{member.user.nickname}님이 {member.companion.title}에 참여했습니다.', 'created_at': member.created_at})
        for inquiry in Inquiry.objects.filter(user=request.user, status='answered').order_by('-updated_at')[:50]:
            items.append({'id': f'inquiry-{inquiry.pk}', 'title': '문의 답변', 'body': inquiry.subject, 'created_at': inquiry.updated_at})
        items.sort(key=lambda item: item['created_at'], reverse=True)
        return success_response({'items': items[:50]})
