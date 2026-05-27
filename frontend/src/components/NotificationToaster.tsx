import { BellRing, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getNotifications, markNotificationRead } from '../services/api';
import { useMissionContext } from '../context/MissionContext';
import type { NotificationItem } from '../types';

const STORAGE_KEY = 'seenNotificationToastIds';

function readSeenIds() {
  try {
    return new Set(JSON.parse(sessionStorage.getItem(STORAGE_KEY) || '[]') as string[]);
  } catch {
    return new Set<string>();
  }
}

function saveSeenIds(ids: Set<string>) {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(ids).slice(-200)));
}

function notificationDestination(notification: NotificationItem) {
  if (notification.related_entity_type === 'observation') return '/observations';
  if (notification.related_entity_type === 'report') return '/report';
  return notification.mission_id ? '/' : '/notifications';
}

export default function NotificationToaster() {
  const navigate = useNavigate();
  const { setActiveMissionId } = useMissionContext();
  const seenIdsRef = useRef<Set<string>>(readSeenIds());
  const initializedRef = useRef(false);
  const [toasts, setToasts] = useState<NotificationItem[]>([]);

  useEffect(() => {
    let isMounted = true;

    const load = async () => {
      try {
        const notifications = await getNotifications();
        const unread = notifications.filter((notification) => !notification.is_read);
        const nextUnread = unread.filter(
          (notification) => !seenIdsRef.current.has(notification.notification_id)
        );

        unread.forEach((notification) => seenIdsRef.current.add(notification.notification_id));
        saveSeenIds(seenIdsRef.current);

        if (!isMounted) return;

        if (!initializedRef.current) {
          initializedRef.current = true;
          return;
        }

        if (nextUnread.length > 0) {
          setToasts((current) => {
            const merged = [...nextUnread.slice(0, 3), ...current];
            const deduped = merged.filter(
              (notification, index, list) =>
                list.findIndex((item) => item.notification_id === notification.notification_id) === index
            );
            return deduped.slice(0, 3);
          });
        }
      } catch (error) {
        console.error('Failed to poll notifications:', error);
      }
    };

    void load();
    const intervalId = window.setInterval(() => {
      void load();
    }, 10000);

    return () => {
      isMounted = false;
      window.clearInterval(intervalId);
    };
  }, []);

  useEffect(() => {
    if (toasts.length === 0) return;
    const timeoutId = window.setTimeout(() => {
      setToasts((current) => current.slice(0, -1));
    }, 7000);
    return () => window.clearTimeout(timeoutId);
  }, [toasts]);

  const openToast = async (notification: NotificationItem) => {
    try {
      await markNotificationRead(notification.notification_id);
    } catch (error) {
      console.error('Failed to mark notification as read:', error);
    }

    setToasts((current) =>
      current.filter((item) => item.notification_id !== notification.notification_id)
    );

    if (notification.mission_id) {
      setActiveMissionId(notification.mission_id);
    }
    navigate(notificationDestination(notification));
  };

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-6 right-6 z-50 flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-3">
      {toasts.map((notification) => (
        <div
          key={notification.notification_id}
          className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl"
        >
          <div className="flex gap-3 p-4">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-[#fff3eb] text-[#ef5b0c]">
              <BellRing className="h-5 w-5" />
            </div>
            <button
              type="button"
              onClick={() => void openToast(notification)}
              className="min-w-0 flex-1 text-left"
            >
              <p className="text-sm font-semibold text-slate-950">{notification.title}</p>
              <p className="mt-1 line-clamp-2 text-sm leading-5 text-slate-600">{notification.message}</p>
            </button>
            <button
              type="button"
              onClick={() =>
                setToasts((current) =>
                  current.filter((item) => item.notification_id !== notification.notification_id)
                )
              }
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
              aria-label="Dismiss notification"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="h-1 bg-gradient-to-r from-[#ef5b0c] via-[#ffb600] to-[#c74634]" />
        </div>
      ))}
    </div>
  );
}
