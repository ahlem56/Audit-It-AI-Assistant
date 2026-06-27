import { MessageCircle } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';

export default function FloatingChatButton() {
  const { pathname } = useLocation();

  if (pathname === '/chat') return null;

  return (
    <Link
      to="/chat"
      className="pwc-floating-chat"
      aria-label="Open AI assistant chat"
    >
      <span className="pwc-floating-chat-tooltip" aria-hidden="true">
        Ask the AI assistant
      </span>
      <span className="pwc-floating-chat-icon" aria-hidden="true">
        <MessageCircle strokeWidth={2.15} />
      </span>
    </Link>
  );
}
