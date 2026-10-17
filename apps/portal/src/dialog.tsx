import { useEffect, useRef, type ReactNode } from "react";

const FOCUSABLE_SELECTOR = "a[href], button, input, select, textarea, [tabindex]";

type DialogProps = {
  children: ReactNode;
  label: string;
  onClose: () => void;
};

function getFocusableElements(container: HTMLElement) {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
    (element) =>
      element.tabIndex >= 0 &&
      !element.hasAttribute("disabled") &&
      !element.matches(":disabled") &&
      !element.hidden &&
      !element.closest("[hidden], [aria-hidden='true']") &&
      element.getAttribute("aria-hidden") !== "true" &&
      !(element instanceof HTMLInputElement && element.type === "hidden"),
  );
}

export function Dialog({ children, label, onClose }: DialogProps) {
  const modalRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    const modal = modalRef.current;
    if (!modal) return;

    const previousFocus = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const focusable = getFocusableElements(modal);
    (focusable[0] ?? modal).focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        if (event.defaultPrevented) return;
        event.preventDefault();
        event.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") return;

      const elements = getFocusableElements(modal);
      if (elements.length === 0) {
        event.preventDefault();
        modal.focus();
        return;
      }

      const activeIndex = elements.indexOf(document.activeElement as HTMLElement);
      if (event.shiftKey && activeIndex <= 0) {
        event.preventDefault();
        elements[elements.length - 1].focus();
      } else if (!event.shiftKey && (activeIndex === -1 || activeIndex === elements.length - 1)) {
        event.preventDefault();
        elements[0].focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      if (previousFocus?.isConnected) {
        previousFocus.focus();
      }
    };
  }, []);

  return (
    <div
      className="modal-backdrop"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={modalRef}
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={label}
        tabIndex={-1}
      >
        {children}
      </div>
    </div>
  );
}
