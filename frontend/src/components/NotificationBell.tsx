import { BellRing } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getNotifications } from '../services/api';
import type { NotificationItem } from '../types';

export default function NotificationBell() {
  const navigate = useNavigate();
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);

  const unreadCount = useMemo(
    () => notifications.filter((notification) => !notification.is_read).length,
    [notifications]
  );

  useEffect(() => {
    let isMounted = true;

    const load = async () => {
      try {
        const data = await getNotifications();
        if (isMounted) {
          setNotifications(data);
        }
      } catch (error) {
        console.error('Failed to load notification count:', error);
      }
    };

    void load();
    const intervalId = window.setInterval(() => {
      void load();
    }, 30000);

    return () => {
      isMounted = false;
      window.clearInterval(intervalId);
    };
  }, []);

  return (
    <button
      type="button"
      onClick={() => navigate('/notifications')}
      className="relative z-[1] flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-slate-200 bg-white/90 text-slate-700 shadow-sm transition hover:border-[#ef5b0c]/40 hover:bg-white hover:text-[#ef5b0c] focus:outline-none focus:ring-2 focus:ring-[#ef5b0c]/20"
      aria-label="Open notifications"
      title="Notifications"
    >
      <BellRing className="h-4 w-4" />
      {unreadCount > 0 && (
        <span className="absolute -right-1 -top-1 min-w-5 rounded-full bg-[#ef5b0c] px-1.5 py-0.5 text-center text-[10px] font-bold leading-none text-white shadow">
          {unreadCount > 9 ? '9+' : unreadCount}
        </span>
      )}
    </button>
  );
}
