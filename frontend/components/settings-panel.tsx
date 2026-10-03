"use client";

import { useEffect, useRef, useState, type ChangeEvent } from "react";
import Link from "next/link";
import { apiBase, type Profile } from "@/lib/api";
import { Icon } from "@/components/ui";
import { ProfileForm } from "@/components/profile-form";

type Account = { user_id: string; email: string | null; is_admin: boolean };
type Tab = "personal" | "notifications" | "permissions";

type StoredSettings = {
  avatar: string;
  location: string;
  instruction: string;
  notifications: { secretMessage: boolean; qualification: boolean };
  permissions: { messages: boolean; teamStatus: boolean; progress: boolean };
};

const storageKey = "campusmate.settings";
const defaults: StoredSettings = {
  avatar: "",
  location: "",
  instruction: "",
  notifications: { secretMessage: true, qualification: true },
  permissions: { messages: true, teamStatus: false, progress: true },
};

function getStoredSettings(): StoredSettings {
  if (typeof window === "undefined") return defaults;
  try {
    const raw = window.localStorage.getItem(storageKey);
    if (!raw) return defaults;
    const parsed = JSON.parse(raw) as Partial<StoredSettings>;
    return {
      ...defaults,
      ...parsed,
      notifications: { ...defaults.notifications, ...parsed.notifications },
      permissions: { ...defaults.permissions, ...parsed.permissions },
    };
  } catch {
    return defaults;
  }
}

function profilePayload(profile: Profile, displayName: string) {
  return {
    display_name: displayName.trim() || profile.display_name,
    discoverable: profile.discoverable,
    school: profile.school,
    college: profile.college,
    grade: profile.grade,
    major: profile.major,
    interests: profile.interests,
    skills: profile.skills,
    weekly_hours: profile.weekly_hours,
    degree: profile.degree,
    target_year: profile.target_year,
    target_path: profile.target_path,
    target_region: profile.target_region,
    language_score: profile.language_score,
    research_exp: profile.research_exp,
    internship_exp: profile.internship_exp,
    competition_exp: profile.competition_exp,
    startup_exp: profile.startup_exp,
  };
}

export function SettingsPanel({ initialProfile, account, initialTab = "personal" }: { initialProfile: Profile; account: Account; initialTab?: Tab }) {
  const [tab, setTab] = useState<Tab>(initialTab);
  const [settings, setSettings] = useState<StoredSettings>(defaults);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => setSettings(getStoredSettings()), []);
  useEffect(() => setTab(initialTab), [initialTab]);

  function persist(next: StoredSettings) {
    setSettings(next);
    try { window.localStorage.setItem(storageKey, JSON.stringify(next)); } catch { /* storage is optional */ }
  }

  function updateField<K extends keyof StoredSettings>(key: K, value: StoredSettings[K]) {
    persist({ ...settings, [key]: value });
  }

  function updateToggle(section: "notifications" | "permissions", key: string, value: boolean) {
    persist({ ...settings, [section]: { ...settings[section], [key]: value } });
  }

  function onAvatarChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith("image/") || file.size > 2 * 1024 * 1024) {
      setError("Choose an image smaller than 2 MB.");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") {
        updateField("avatar", reader.result);
        setError("");
      }
    };
    reader.onerror = () => setError("The image could not be read.");
    reader.readAsDataURL(file);
  }

  function downloadProfile() {
    const data = { ...profilePayload(initialProfile, initialProfile.display_name), location: settings.location, instruction: settings.instruction };
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url; link.download = "campusmate-profile.json"; link.click();
    URL.revokeObjectURL(url);
  }

  async function signOut(next = "/login") {
    if (busy) return;
    setBusy(true); setError("");
    try {
      await fetch("/api/session", { method: "DELETE" });
      window.location.href = next;
    } catch {
      setError("Could not end the session. Please try again.");
      setBusy(false);
    }
  }

  const email = account.email || "Demo account · email unavailable";
  const tabs: { id: Tab; label: string; icon: "file" | "bell" | "shield" }[] = [
    { id: "personal", label: "Personal files", icon: "file" },
    { id: "notifications", label: "Notifications", icon: "bell" },
    { id: "permissions", label: "Permissions", icon: "shield" },
  ];

  return (
    <section className="settings-workspace" aria-label="Settings workspace">
      <div className="settings-tabs" role="tablist" aria-label="Settings sections">
        {tabs.map((item) => (
          <Link key={item.id} href={`/settings?section=${item.id}`} scroll={false} role="tab" aria-selected={tab === item.id} className={`settings-tab ${tab === item.id ? "active" : ""}`} onClick={() => setTab(item.id)}>
            <Icon name={item.icon} size={16} /> <span>{item.label}</span>
          </Link>
        ))}
      </div>

      {tab === "personal" && <div className="settings-content" role="tabpanel">
        <div className="settings-section-head"><div><p className="eyebrow">PERSONAL FILES</p><h2>Profile and account</h2><p>Keep the details that shape your workspace in one place.</p></div><button className="button secondary" type="button" onClick={downloadProfile}><Icon name="file" size={15} />Download profile</button></div>
        <div className="settings-profile-grid">
          <div className="settings-fields">
            <div className="settings-inline"><div><span className="settings-label">Your email</span><strong>{email}</strong></div><div><span className="settings-label">Account ID</span><strong className="settings-id">{account.user_id}</strong></div></div>
            <label className="settings-field"><span>Location</span><input value={settings.location} maxLength={80} placeholder="Add your city or region" onChange={(event) => updateField("location", event.target.value)} /></label>
            <label className="settings-field"><span>Personal instruction</span><textarea value={settings.instruction} maxLength={1000} placeholder="Tell CampusMate how to support your next step." onChange={(event) => updateField("instruction", event.target.value)} /></label>
          </div>
          <div className="settings-avatar-panel"><span className="settings-label">Profile picture</span><div className="settings-avatar">{settings.avatar ? <img src={settings.avatar} alt="" /> : <span>{(initialProfile.display_name || "C").slice(0, 1).toUpperCase()}</span>}</div><input ref={fileInput} className="sr-only" type="file" accept="image/png,image/jpeg,image/webp" onChange={onAvatarChange} /><button className="button secondary" type="button" onClick={() => fileInput.current?.click()}><Icon name="plus" size={14} />Choose picture</button>{settings.avatar && <button className="settings-remove" type="button" onClick={() => updateField("avatar", "")}>Remove picture</button>}<small>PNG, JPG, or WEBP up to 2 MB. Stored on this device.</small></div>
        </div>
        <div className="settings-profile-form"><ProfileForm initial={initialProfile} /></div>
        <div className="settings-account-actions"><button className="button secondary" type="button" onClick={() => void signOut("/login?switch=1")} disabled={busy}><Icon name="users" size={15} />Switch account</button><button className="button danger" type="button" onClick={() => void signOut()} disabled={busy}><Icon name="logout" size={15} />Log out</button></div>
      </div>}

      {tab === "notifications" && <div className="settings-content" role="tabpanel"><div className="settings-section-head"><div><p className="eyebrow">NOTIFICATIONS</p><h2>Choose what reaches your inbox</h2><p>Changes take effect immediately on this device.</p></div></div><div className="settings-list">{([ ["secretMessage", "Secret message sent to you", "Keep private messages visible in your notification center."], ["qualification", "Qualification check finished", "Know when a qualification review has a result."] ] as const).map(([key, title, description]) => <label className="settings-option" key={key}><span><strong>{title}</strong><small>{description}</small></span><input type="checkbox" checked={settings.notifications[key]} onChange={(event) => updateToggle("notifications", key, event.target.checked)} /></label>)}</div></div>}

      {tab === "permissions" && <div className="settings-content" role="tabpanel"><div className="settings-section-head"><div><p className="eyebrow">PERMISSIONS</p><h2>Control how your workspace is shared</h2><p>Turn on only the collaboration signals you want other people to see.</p></div></div><div className="settings-list">{([ ["messages", "Send messages to you", "Allow teammates to start a workspace conversation."], ["teamStatus", "Show your team status", "Let teammates see whether you are available for collaboration."], ["progress", "Show your way progress", "Share a high-level view of your progress on a chosen path."] ] as const).map(([key, title, description]) => <label className="settings-option" key={key}><span><strong>{title}</strong><small>{description}</small></span><input type="checkbox" checked={settings.permissions[key]} onChange={(event) => updateToggle("permissions", key, event.target.checked)} /></label>)}</div></div>}
      {error && <p className="settings-error" role="alert">{error}</p>}
    </section>
  );
}
