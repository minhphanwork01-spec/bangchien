(function () {
  function setupVariantFilter() {
    const classSelect = document.getElementById("id_class_name");
    const variantSelect = document.getElementById("id_class_variant");

    if (!classSelect || !variantSelect) return;

    const validVariants = {
      "Thiết Y": ["Ngự", "Phá"],
      "Tố Vấn": ["Thiên Vấn", "Tố Tâm"],
    };

    const originalOptions = Array.from(variantSelect.options).map(option => ({
      value: option.value,
      text: option.text,
    }));

    function rebuildVariantOptions() {
      const selectedClass = classSelect.value;
      const currentVariant = variantSelect.value;
      const allowed = validVariants[selectedClass] || [];

      variantSelect.innerHTML = "";

      const emptyOption = originalOptions.find(optionData => optionData.value === "");
      if (emptyOption) {
        const option = document.createElement("option");
        option.value = emptyOption.value;
        option.text = emptyOption.text;
        variantSelect.appendChild(option);
      }

      allowed.forEach(value => {
        const optionData = originalOptions.find(item => item.value === value);
        if (!optionData) return;
        const option = document.createElement("option");
        option.value = optionData.value;
        option.text = optionData.text;
        variantSelect.appendChild(option);
      });

      if (allowed.length === 0) {
        variantSelect.value = "";
        variantSelect.disabled = true;
      } else {
        variantSelect.disabled = false;
        variantSelect.value = allowed.includes(currentVariant) ? currentVariant : "";
      }
    }

    classSelect.addEventListener("change", rebuildVariantOptions);
    rebuildVariantOptions();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setupVariantFilter);
  } else {
    setupVariantFilter();
  }
})();
