export const WELCOME_DATA = {
  systemStatus: {
    label: 'SYSTEM STATUS',
    workspaceLabel: 'Workspace: ',
  },
} as const;

function getTimeOfDay(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'Morning';
  if (hour < 18) return 'Afternoon';
  return 'Evening';
}

function getSystemUsername(): string {
  return process.env.USERNAME || process.env.USER || 'Operator';
}

export const getGreeting = (): string => {
  const username = getSystemUsername();
  const timeOfDay = getTimeOfDay();
  return `Good ${timeOfDay}, ${username}`;
};
