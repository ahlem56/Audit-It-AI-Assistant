import { BellRing, CheckCheck, FileText, Layers, ListChecks, ShieldCheck } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getNotifications, markAllNotificationsRead, markNotificationRead } from '../services/api';
import { useMissionContext } from '../context/MissionContext';
import type { NotificationItem } from '../types';

const notificationIcons: Record<string, typeof BellRing> = {
  mission_assigned: ShieldCheck,
  mission_status_changed: ListChecks,
  observation_created: Layers,
  report_generated: FileText,
  report_finalized: CheckCheck
};

function formatNotificationTime(value: string) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  }).format(date);
}

function notificationDestination(notification: NotificationItem) {
  if (notification.related_entity_type === 'observation') return '/observations';
  if (notification.related_entity_type === 'report') return '/report';
  return '/';
}

export default function NotificationsPage() {
  const navigate = useNavigate();
  const { setActiveMissionId } = useMissionContext();
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(true);

  const unreadCount = useMemo(
    () => notifications.filter((notification) => !notification.is_read).length,
    [notifications]
  );

  const loadNotifications = async () => {
    setLoading(true);
    try {
      setNotifications(await getNotifications());
    } catch (error) {
      console.error('Failed to load notifications:', error);
      setNotifications([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadNotifications();
  }, []);

  const openNotification = async (notification: NotificationItem) => {
    if (!notification.is_read) {
      try {
        const updated = await markNotificationRead(notification.notification_id);
        setNotifications((current) =>
          current.map((item) => (item.notification_id === updated.notification_id ? updated : item))
        );
      } catch (error) {
        console.error('Failed to mark notification as read:', error);
      }
    }

    if (notification.mission_id) {
      setActiveMissionId(notification.mission_id);
    }
    navigate(notificationDestination(notification));
  };

  const markAllRead = async () => {
    try {
      await markAllNotificationsRead();
      setNotifications((current) =>
        current.map((notification) => ({
          ...notification,
          is_read: true,
          read_at: notification.read_at || new Date().toISOString()
        }))
      );
    } catch (error) {
      console.error('Failed to mark notifications as read:', error);
    }
  };

  return (
    <div className="relative z-[1] space-y-6">
      <section className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="pwc-kicker">Activity center</p>
          <h1 className="pwc-title mt-3 text-4xl font-semibold">Notifications</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600">
            Track mission assignments, status changes, new observations, and report updates.
          </p>
        </div>

        <button
          type="button"
          onClick={() => void markAllRead()}
          disabled={unreadCount === 0}
          className="pwc-action-muted justify-center disabled:cursor-not-allowed disabled:opacity-50"
        >
          <CheckCheck className="h-4 w-4" />
          Mark all read
        </button>
      </section>

      <section className="pwc-main-panel p-0">
        <div className="flex items-center justify-between border-b border-slate-200/80 px-6 py-5">
          <div>
            <p className="text-sm font-semibold text-slate-950">Recent notifications</p>
            <p className="mt-1 text-xs text-slate-500">
              {unreadCount} unread of {notifications.length}
            </p>
          </div>
          <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#fff3eb] text-[#ef5b0c]">
            <BellRing className="h-5 w-5" />
          </span>
        </div>

        <div className="divide-y divide-slate-100">
          {notifications.map((notification) => {
            const Icon = notificationIcons[notification.type] ?? BellRing;
            return (
              <button
                key={notification.notification_id}
                type="button"
                onClick={() => void openNotification(notification)}
                className={`flex w-full gap-4 px-6 py-5 text-left transition hover:bg-slate-50 ${
                  notification.is_read ? 'bg-white/40' : 'bg-[#fffaf6]'
                }`}
              >
                <span
                  className={`mt-0.5 flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl ${
                    notification.is_read ? 'bg-slate-100 text-slate-500' : 'bg-[#fff3eb] text-[#ef5b0c]'
                  }`}
                >
                  <Icon className="h-5 w-5" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-start justify-between gap-4">
                    <span className="text-sm font-semibold text-slate-950">{notification.title}</span>
                    {!notification.is_read && (
                      <span className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full bg-[#ef5b0c]" />
                    )}
                  </span>
                  <span className="mt-1 block text-sm leading-6 text-slate-600">{notification.message}</span>
                  <span className="mt-3 block text-xs font-medium uppercase tracking-[0.14em] text-slate-400">
                    {formatNotificationTime(notification.created_at)}
                  </span>
                </span>
              </button>
            );
          })}

          {notifications.length === 0 && (
            <div className="px-6 py-14 text-center">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-slate-500">
                <BellRing className="h-5 w-5" />
              </div>
              <p className="mt-4 text-sm font-semibold text-slate-900">
                {loading ? 'Loading notifications...' : 'No notifications yet'}
              </p>
              <p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-slate-500">
                Mission, observation, and report alerts will appear here when activity happens.
              </p>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
