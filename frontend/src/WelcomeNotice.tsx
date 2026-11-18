import { useState } from "react";
import { Button, Drawer } from "antd";

export function WelcomeNotice({
  onGuide,
}: {
  onGuide: () => void;
}) {
  const [announcements, setAnnouncements] = useState(false);
  return (
    <>
      <Button
        aria-label="通知与公告"
        title="通知与公告"
        onClick={() => setAnnouncements(true)}
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          aria-hidden="true"
        >
          <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9Z" />
          <path d="M10 21h4" />
        </svg>
      </Button>
      <Drawer
        title="通知与公告"
        open={announcements}
        onClose={() => setAnnouncements(false)}
        width={360}
      >
        <Button
          block
          onClick={() => {
            setAnnouncements(false);
            onGuide();
          }}
        >
          使用指南
        </Button>
      </Drawer>

    </>
  );
}
