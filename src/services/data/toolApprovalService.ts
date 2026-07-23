import { loadUserProfile } from './userProfileService';

export function isAutoApproveEnabled(): boolean {
  const profile = loadUserProfile();
  return Boolean(profile.settings?.autoApproveTools ?? profile.autoApproveTools);
}

export function requiresApproval(eventKind: string): boolean {
  const approvalKinds = [
    'terminal',
    'file_create',
    'file_edit',
    'file_delete',
    'build_step',
    'test_execution',
    'deployment',
  ];
  return approvalKinds.includes(eventKind);
}
