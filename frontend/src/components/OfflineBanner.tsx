import { useOnline } from "../pwa";

export default function OfflineBanner() {
  const online = useOnline();
  if (online) return null;
  return (
    <div className="offline-banner" role="status">
      You’re offline. Open pages already loaded on this device, but changes are not saved until you’re back online.
    </div>
  );
}
