export const dynamic = "force-dynamic";

export default function PublicHome() {
  return (
    <iframe
      title="CampusMate public home"
      src="/landing/index.html"
      style={{ border: 0, display: "block", height: "100vh", width: "100%" }}
    />
  );
}
