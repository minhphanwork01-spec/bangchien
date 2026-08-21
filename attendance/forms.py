"""
Forms cho yêu cầu thành viên.

Attendance không dùng ModelForm vì logic submit được xử lý trực tiếp trong view.
"""

from django import forms

from .models import VALID_CLASS_VARIANTS, Member, MemberRequest, normalize_search_name

# Một nguồn sự thật duy nhất cho variant hợp lệ (định nghĩa trong models).
VALID_VARIANTS = VALID_CLASS_VARIANTS


def _clean_variant(cleaned):
    class_name = cleaned.get("class_name")
    class_variant = cleaned.get("class_variant")
    allowed = VALID_VARIANTS.get(class_name, set())
    if class_variant and class_variant not in allowed:
        cleaned["class_variant"] = ""
    return cleaned


def _duplicate_name_exists(name, *, exclude_member=None):
    normalized = normalize_search_name(name)
    queryset = Member.objects.all()
    if exclude_member is not None:
        queryset = queryset.exclude(pk=exclude_member.pk)
    return queryset.filter(search_name=normalized).exists()


class MemberRequestForm(forms.ModelForm):
    """Form public để đề nghị tạo nhân vật mới."""

    class Meta:
        model = MemberRequest
        fields = ["requested_name", "class_name", "class_variant", "note"]
        labels = {
            "requested_name": "Tên nhân vật trong game",
            "class_name": "Phái",
            "class_variant": "Hệ/phân nhánh",
            "note": "Ghi chú thêm",
        }
        widgets = {
            "requested_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Nhập đúng tên nhân vật trong game",
                    "autocomplete": "off",
                }
            ),
            "class_name": forms.Select(attrs={"class": "form-select"}),
            "class_variant": forms.Select(attrs={"class": "form-select"}),
            "note": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Thông tin để leader xác minh...",
                }
            ),
        }

    def clean(self):
        cleaned = _clean_variant(super().clean())
        name = (cleaned.get("requested_name") or "").strip()
        if name and _duplicate_name_exists(name):
            self.add_error("requested_name", "Tên nhân vật này đã có trong danh sách.")
        return cleaned

    def clean_requested_name(self):
        name = (self.cleaned_data.get("requested_name") or "").strip()
        if len(name) < 2:
            raise forms.ValidationError("Tên nhân vật phải có ít nhất 2 ký tự.")
        return name

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.request_type = MemberRequest.RequestType.ADD
        if commit:
            instance.save()
        return instance


class MemberUpdateRequestForm(forms.Form):
    """
    Form public để đề nghị sửa thông tin Member đang chọn.

    Form được preload tên/phái hiện tại. Field không đổi sẽ được giữ nguyên.
    """

    requested_name = forms.CharField(
        label="Tên nhân vật",
        max_length=100,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "autocomplete": "off",
            }
        ),
    )
    class_name = forms.ChoiceField(
        label="Phái",
        choices=Member.ClassName.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    class_variant = forms.ChoiceField(
        label="Hệ/phân nhánh",
        choices=[("", "Không có")] + list(Member.ClassVariant.choices),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    note = forms.CharField(
        label="Ghi chú cho leader",
        required=False,
        max_length=1000,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Có thể để trống nếu thay đổi đã rõ ràng.",
            }
        ),
    )

    def __init__(self, *args, member, **kwargs):
        self.member = member
        if not args and "initial" not in kwargs:
            kwargs["initial"] = {
                "requested_name": member.display_name,
                "class_name": member.class_name,
                "class_variant": member.class_variant,
            }
        super().__init__(*args, **kwargs)

    def clean_requested_name(self):
        name = (self.cleaned_data.get("requested_name") or "").strip()
        if len(name) < 2:
            raise forms.ValidationError("Tên nhân vật phải có ít nhất 2 ký tự.")
        if _duplicate_name_exists(name, exclude_member=self.member):
            raise forms.ValidationError("Tên nhân vật này đã được sử dụng.")
        return name

    def clean(self):
        cleaned = _clean_variant(super().clean())
        if self.errors:
            return cleaned

        requested_name = cleaned.get("requested_name", "")
        class_name = cleaned.get("class_name", "")
        class_variant = cleaned.get("class_variant", "")

        has_change = (
            requested_name != self.member.display_name
            or class_name != self.member.class_name
            or class_variant != self.member.class_variant
        )
        if not has_change:
            raise forms.ValidationError("Bạn chưa thay đổi thông tin nào.")

        pending_exists = MemberRequest.objects.filter(
            request_type=MemberRequest.RequestType.UPDATE,
            target_member=self.member,
            status=MemberRequest.Status.PENDING,
        ).exists()
        if pending_exists:
            raise forms.ValidationError(
                "Nhân vật này đã có một yêu cầu thay đổi đang chờ leader duyệt."
            )
        return cleaned

    def save(self):
        return MemberRequest.objects.create(
            request_type=MemberRequest.RequestType.UPDATE,
            target_member=self.member,
            requested_name=self.cleaned_data["requested_name"],
            class_name=self.cleaned_data["class_name"],
            class_variant=self.cleaned_data.get("class_variant", ""),
            original_name=self.member.display_name,
            original_class_name=self.member.class_name,
            original_class_variant=self.member.class_variant,
            note=self.cleaned_data.get("note", ""),
        )
