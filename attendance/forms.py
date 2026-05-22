"""
attendance/forms.py

Forms cho bangcheck. Chủ yếu dùng cho MemberRequest.
Attendance không dùng ModelForm vì logic submit được xử lý trực tiếp trong view.
"""

from django import forms
from .models import MemberRequest


class MemberRequestForm(forms.ModelForm):
    """
    Form để thành viên yêu cầu thêm vào danh sách.
    BR4/BR5: Không tự động tạo Member, chỉ tạo MemberRequest pending.

    Không hỏi team cố định vì squad/team sẽ do leader xếp theo từng tuần.
    """

    class Meta:
        model = MemberRequest
        fields = ["requested_name", "class_name", "class_variant", "note"]
        labels = {
            "requested_name": "Tên nhân vật trong game",
            "class_name": "Phái",
            "class_variant": "Hệ/phân nhánh",
            "note": "Ghi chú thêm (để leader dễ xác minh)",
        }
        widgets = {
            "requested_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Nhập đúng tên nhân vật trong game"}
            ),
            "class_name": forms.Select(attrs={"class": "form-select"}),
            "class_variant": forms.Select(attrs={"class": "form-select"}),
            "note": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Thông tin thêm để leader xác minh bạn là ai...",
                }
            ),
        }

    def clean(self):
        cleaned = super().clean()
        class_name = cleaned.get("class_name")
        class_variant = cleaned.get("class_variant")

        valid_variants = {
            "Thiết Y": {"Phá", "Ngự"},
            "Tố Vấn": {"Thiên Vấn", "Tố Tâm"},
        }
        allowed = valid_variants.get(class_name, set())

        if class_variant and class_variant not in allowed:
            cleaned["class_variant"] = ""

        return cleaned

    def clean_requested_name(self):
        name = self.cleaned_data.get("requested_name", "").strip()
        if not name:
            raise forms.ValidationError("Vui lòng nhập tên nhân vật.")
        if len(name) < 2:
            raise forms.ValidationError("Tên nhân vật phải có ít nhất 2 ký tự.")
        return name
