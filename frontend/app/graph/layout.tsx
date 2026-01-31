import { AppShell } from '@/components/layout/AppShell';
import { Sidebar } from '@/components/layout/Sidebar';

/**
 * Layout for the /graph route. Shares the same AppShell + Sidebar as /docs
 * but with no padding on the main content area so reactflow can fill
 * the entire viewport.
 */
export default function GraphLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AppShell sidebar={<Sidebar />}>
      {children}
    </AppShell>
  );
}
