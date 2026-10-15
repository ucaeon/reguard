import React, { useEffect, useRef, useState } from "react";
import { ownedEditPayload, changeOwnedProduct } from "./owned-products.js";
export default function OwnedProductDialog({ item, mode, onClose, onSuccess }) {
  const dialog = useRef(null),
    locked = useRef(false);
  const [values, setValues] = useState(() =>
    Object.fromEntries(
      [
        "productName",
        "companyName",
        "modelName",
        "identifierType",
        "identifierValue",
        "expiryDate",
        "lotNumber",
      ].map((key) => [key, item[key] || ""]),
    ),
  );
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const deleting = mode === "delete",
    catalog = item.registrationType === "CATALOG";
  useEffect(() => {
    const focused = document.activeElement,
      overflow = document.body.style.overflow;
    dialog.current.showModal();
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = overflow;
      if (focused?.isConnected) focused.focus();
    };
  }, []);
  async function submit(e) {
    e.preventDefault();
    if (locked.current) return;
    setError("");
    try {
      const payload = deleting ? undefined : ownedEditPayload(item, values);
      locked.current = true;
      setBusy(true);
      await changeOwnedProduct(item.id, deleting ? "DELETE" : "PATCH", payload);
      onSuccess(deleting ? "물건을 삭제했어요." : "등록 정보를 수정했어요.");
    } catch (e) {
      setError(e.message);
    } finally {
      locked.current = false;
      setBusy(false);
    }
  }
  function field(name, label, type = "text", required = false) {
    return (
      <label className="mi-edit-field">
        {label}
        <input
          name={name}
          type={type}
          required={required}
          maxLength={
            ["identifierValue", "lotNumber"].includes(name) ? 255 : 500
          }
          value={values[name]}
          onChange={(e) => setValues({ ...values, [name]: e.target.value })}
        />
      </label>
    );
  }
  return (
    <dialog
      ref={dialog}
      className="mi-dialog"
      aria-labelledby="mi-dialog-title"
      onCancel={(e) => {
        e.preventDefault();
        if (!locked.current) onClose();
      }}
    >
      <form onSubmit={submit}>
        <h2 id="mi-dialog-title">
          {deleting ? "이 물건을 삭제할까요?" : "등록 정보 수정"}
        </h2>
        {deleting ? (
          <>
            <p className="mi-delete-name">{item.productName}</p>
            <p className="mi-dialog-note">
              내 물건 목록에서 삭제돼요. 다시 관리하려면 새로 등록해야 해요.
            </p>
          </>
        ) : (
          <fieldset disabled={busy}>
            {catalog ? (
              <>
                <p className="mi-delete-name">{item.productName}</p>
                <p className="mi-dialog-note">
                  검색으로 등록한 제품은 소비기한과 제조번호를 수정할 수 있어요.
                </p>
              </>
            ) : (
              <>
                {field("productName", "제품명", "text", true)}
                {field("companyName", "제조·수입업체명")}
                {field("modelName", "모델명")}
                <label className="mi-edit-field">
                  식별번호 종류
                  <select
                    value={values.identifierType}
                    onChange={(e) =>
                      setValues({ ...values, identifierType: e.target.value })
                    }
                  >
                    <option value="">선택 안 함</option>
                    <option value="FOOD_REPORT_NO">품목보고번호</option>
                    <option value="KC_CERT_NO">KC 인증번호</option>
                    <option value="BARCODE">바코드</option>
                  </select>
                </label>
                {field("identifierValue", "식별번호")}
              </>
            )}
            {field("expiryDate", "소비기한", "date")}
            {field("lotNumber", "제조번호 (LOT)")}
          </fieldset>
        )}
        {error && (
          <p className="mi-dialog-error" role="alert">
            {error}
          </p>
        )}
        <div className="mi-dialog-actions">
          <button type="button" disabled={busy} onClick={onClose}>
            취소
          </button>
          <button
            type="submit"
            className={deleting ? "mi-delete-confirm" : "mi-save-confirm"}
            disabled={busy}
          >
            {busy ? "처리 중…" : deleting ? "삭제" : "저장"}
          </button>
        </div>
      </form>
    </dialog>
  );
}
