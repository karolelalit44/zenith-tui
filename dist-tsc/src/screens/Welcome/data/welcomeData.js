export const WELCOME_DATA = {
    systemStatus: {
        label: 'SYSTEM STATUS',
        workspaceLabel: 'Workspace: ',
    },
};
function getSystemUsername() {
    return process.env.USERNAME || process.env.USER || 'User';
}
export const GREETINGS = {
    morning: 'Compiling coffee...',
    afternoon: 'Midday grind.',
    evening: 'Sun is down, screens are bright.',
    night: (user) => `Burning the midnight oil, ${user}?`,
};
export const getGreeting = () => {
    const username = getSystemUsername();
    const hour = new Date().getHours();
    if (hour >= 5 && hour < 12) {
        return GREETINGS.morning;
    }
    if (hour >= 12 && hour < 17) {
        return GREETINGS.afternoon;
    }
    if (hour >= 17 && hour < 22) {
        return GREETINGS.evening;
    }
    return GREETINGS.night(username);
};
