"""Business logic for member requests."""

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Member, MemberRequest, normalize_search_name


class MemberRequestError(Exception):
    """A user-safe error raised when a member request cannot be applied."""


def _ensure_unique_name(name, *, exclude_member=None):
    queryset = Member.objects.all()
    if exclude_member is not None:
        queryset = queryset.exclude(pk=exclude_member.pk)
    if queryset.filter(search_name=normalize_search_name(name)).exists():
        raise MemberRequestError("Tên nhân vật này đã tồn tại trong danh sách.")


@transaction.atomic
def approve_member_request(request_id, reviewer, review_note=""):
    """
    Apply one pending request and persist its audit data.

    - add: create Member.
    - update: update the linked Member only after approval.
    """
    member_request = (
        MemberRequest.objects.select_for_update()
        .select_related("target_member")
        .get(pk=request_id)
    )
    if member_request.status != MemberRequest.Status.PENDING:
        raise MemberRequestError("Yêu cầu này đã được xử lý.")

    if member_request.request_type == MemberRequest.RequestType.UPDATE:
        if not member_request.target_member_id:
            raise MemberRequestError("Nhân vật cần chỉnh không còn tồn tại.")

        member = Member.objects.select_for_update().get(
            pk=member_request.target_member_id
        )
        _ensure_unique_name(
            member_request.requested_name,
            exclude_member=member,
        )

        # Preserve the snapshot even if an older request was created without it.
        if not member_request.original_name:
            member_request.original_name = member.display_name
        if not member_request.original_class_name:
            member_request.original_class_name = member.class_name
        if not member_request.original_class_variant:
            member_request.original_class_variant = member.class_variant

        member.display_name = member_request.requested_name
        member.class_name = member_request.class_name
        member.class_variant = member_request.class_variant
        member.save()

        result_message = f"Đã cập nhật thông tin cho {member.display_name}."
    else:
        _ensure_unique_name(member_request.requested_name)
        try:
            member = Member.objects.create(
                display_name=member_request.requested_name,
                class_name=member_request.class_name,
                class_variant=member_request.class_variant,
                note=member_request.note,
                active=True,
            )
        except IntegrityError as exc:
            raise MemberRequestError("Không thể tạo thành viên mới.") from exc
        result_message = f"Đã thêm {member.display_name} vào danh sách thành viên."

    member_request.status = MemberRequest.Status.APPROVED
    member_request.reviewed_by = reviewer
    member_request.reviewed_at = timezone.now()
    member_request.review_note = (review_note or "").strip()
    member_request.save(
        update_fields=[
            "status",
            "reviewed_by",
            "reviewed_at",
            "review_note",
            "original_name",
            "original_class_name",
            "original_class_variant",
            "updated_at",
        ]
    )
    return member_request, member, result_message


@transaction.atomic
def reject_member_request(request_id, reviewer, review_note=""):
    member_request = MemberRequest.objects.select_for_update().get(
        pk=request_id
    )
    if member_request.status != MemberRequest.Status.PENDING:
        raise MemberRequestError("Yêu cầu này đã được xử lý.")

    member_request.status = MemberRequest.Status.REJECTED
    member_request.reviewed_by = reviewer
    member_request.reviewed_at = timezone.now()
    member_request.review_note = (review_note or "").strip()
    member_request.save(
        update_fields=[
            "status",
            "reviewed_by",
            "reviewed_at",
            "review_note",
            "updated_at",
        ]
    )
    return member_request
