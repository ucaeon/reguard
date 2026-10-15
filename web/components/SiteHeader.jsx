import React from "react";
import BrandMark from "../BrandMark.jsx";
import AccountMenu from "../AccountMenu.jsx";
import NotificationNav from "../notifications/NotificationNav.jsx";
import "../styles/header.css";

const menus = [
  ["about", "가이드"],
  ["recalls", "리콜 정보"],
  ["items", "내 물건"],
  ["notifications", "알림"],
  ["settings", "설정"],
];

export function MainNavigation({ active }) {
  return menus.map(([view, label]) =>
    view === "notifications" ? (
      <NotificationNav key={view} />
    ) : (
      <a
        key={view}
        href={`/?view=${view}`}
        aria-current={
          active === view || (view === "recalls" && active === "recall")
            ? "page"
            : undefined
        }
      >
        {label}
      </a>
    ),
  );
}

export default function SiteHeader({ active, variant = "about" }) {
  const logo = (
    <a
      className={variant === "compact" ? "brand" : undefined}
      href="/"
      aria-label="ReGuard 홈"
    >
      <BrandMark />
    </a>
  );
  if (variant === "auth")
    return (
      <header className="auth-header">
        {logo}
        <a className="auth-home" href="/">
          홈으로
        </a>
      </header>
    );
  const content = (
    <>
      {logo}
      <nav className="site-main-nav" aria-label="주 메뉴">
        <MainNavigation active={active} />
      </nav>
      <AccountMenu />
    </>
  );
  return variant === "compact" ? (
    <header>
      <div className="header-inner site-header-layout">{content}</div>
    </header>
  ) : (
    <header className={`${variant}-header site-header-layout`}>
      {content}
    </header>
  );
}
