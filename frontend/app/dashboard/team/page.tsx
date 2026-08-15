"use client";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Loader2, Trash2, UserPlus, Users } from "lucide-react";
import { useAuthStore } from "@/lib/store";
import { orgApi, Organization, OrgMember, OrgRole } from "@/lib/api";

export default function TeamPage() {
  const router = useRouter();
  const { user, loadMe, loading, checked } = useAuthStore();

  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [activeOrgId, setActiveOrgId] = useState<number | null>(null);
  const [members, setMembers] = useState<OrgMember[]>([]);
  const [orgsLoading, setOrgsLoading] = useState(true);
  const [error, setError] = useState("");

  const [newOrgName, setNewOrgName] = useState("");
  const [creating, setCreating] = useState(false);

  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<OrgRole>("member");
  const [inviting, setInviting] = useState(false);

  useEffect(() => {
    loadMe();
  }, [loadMe]);

  useEffect(() => {
    if (checked && !user) router.replace("/auth/login");
  }, [user, checked, router]);

  const refreshOrgs = useCallback(async () => {
    setOrgsLoading(true);
    try {
      const { data } = await orgApi.list();
      setOrgs(data);
      setActiveOrgId((prev) => prev ?? data[0]?.id ?? null);
    } catch {
      setError("Could not load organizations.");
    } finally {
      setOrgsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (user) refreshOrgs();
  }, [user, refreshOrgs]);

  const refreshMembers = useCallback(async (orgId: number) => {
    try {
      const { data } = await orgApi.members(orgId);
      setMembers(data);
    } catch {
      setError("Could not load members.");
    }
  }, []);

  useEffect(() => {
    if (activeOrgId) refreshMembers(activeOrgId);
  }, [activeOrgId, refreshMembers]);

  const myRole = members.find((m) => m.user_id === user?.id)?.role;
  const canManage = myRole === "owner" || myRole === "admin";

  const handleCreateOrg = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setCreating(true);
    try {
      const { data } = await orgApi.create(newOrgName);
      setNewOrgName("");
      await refreshOrgs();
      setActiveOrgId(data.id);
    } catch (err: any) {
      setError(err.response?.data?.detail ?? "Could not create organization.");
    } finally {
      setCreating(false);
    }
  };

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeOrgId) return;
    setError("");
    setInviting(true);
    try {
      await orgApi.invite(activeOrgId, inviteEmail, inviteRole);
      setInviteEmail("");
      await refreshMembers(activeOrgId);
    } catch (err: any) {
      setError(err.response?.data?.detail ?? "Could not invite member.");
    } finally {
      setInviting(false);
    }
  };

  const handleRoleChange = async (userId: number, role: OrgRole) => {
    if (!activeOrgId) return;
    try {
      await orgApi.updateRole(activeOrgId, userId, role);
      await refreshMembers(activeOrgId);
    } catch (err: any) {
      setError(err.response?.data?.detail ?? "Could not update role.");
    }
  };

  const handleRemove = async (userId: number) => {
    if (!activeOrgId) return;
    try {
      await orgApi.removeMember(activeOrgId, userId);
      await refreshMembers(activeOrgId);
    } catch (err: any) {
      setError(err.response?.data?.detail ?? "Could not remove member.");
    }
  };

  if (loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-brand-600 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="border-b border-gray-200 bg-white px-6 py-3">
        <div className="mx-auto flex max-w-7xl items-center gap-4">
          <Link href="/dashboard" className="text-gray-400 hover:text-gray-600">
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <span className="font-semibold text-gray-900">Team</span>
        </div>
      </nav>

      <main className="mx-auto max-w-5xl px-6 py-8">
        {error && (
          <div className="mb-6 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {orgsLoading ? (
          <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
        ) : orgs.length === 0 ? (
          <div className="card max-w-md">
            <Users className="mb-3 h-10 w-10 text-gray-300" />
            <h2 className="font-medium text-gray-900">Create your first organization</h2>
            <p className="mb-4 text-sm text-gray-500">
              Organizations let you share repositories and review access with teammates.
            </p>
            <form onSubmit={handleCreateOrg} className="flex gap-2">
              <input
                className="input"
                placeholder="acme-corp"
                value={newOrgName}
                onChange={(e) => setNewOrgName(e.target.value)}
                required
              />
              <button className="btn-primary shrink-0" disabled={creating}>
                {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : "Create"}
              </button>
            </form>
          </div>
        ) : (
          <>
            <div className="mb-6 flex items-center gap-3">
              <label className="text-sm font-medium text-gray-700">Organization</label>
              <select
                className="input w-auto"
                value={activeOrgId ?? ""}
                onChange={(e) => setActiveOrgId(Number(e.target.value))}
              >
                {orgs.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.display_name ?? o.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="card">
              <h2 className="mb-4 font-medium text-gray-900">Members</h2>
              <ul className="divide-y divide-gray-100">
                {members.map((m) => (
                  <li key={m.user_id} className="flex items-center justify-between py-3">
                    <div>
                      <p className="text-sm font-medium text-gray-800">{m.username}</p>
                      <p className="text-xs text-gray-400">{m.email}</p>
                    </div>
                    <div className="flex items-center gap-3">
                      {canManage && m.role !== "owner" ? (
                        <select
                          className="input w-auto py-1 text-xs"
                          value={m.role}
                          onChange={(e) => handleRoleChange(m.user_id, e.target.value as OrgRole)}
                        >
                          <option value="admin">Admin</option>
                          <option value="member">Member</option>
                        </select>
                      ) : (
                        <span className="badge bg-gray-100 text-gray-600 capitalize">{m.role}</span>
                      )}
                      {canManage && m.role !== "owner" && (
                        <button
                          onClick={() => handleRemove(m.user_id)}
                          className="text-gray-300 hover:text-red-500"
                          title="Remove member"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      )}
                    </div>
                  </li>
                ))}
              </ul>

              {canManage && (
                <form onSubmit={handleInvite} className="mt-6 flex gap-2 border-t border-gray-100 pt-4">
                  <input
                    type="email"
                    className="input"
                    placeholder="teammate@company.com"
                    value={inviteEmail}
                    onChange={(e) => setInviteEmail(e.target.value)}
                    required
                  />
                  <select
                    className="input w-auto"
                    value={inviteRole}
                    onChange={(e) => setInviteRole(e.target.value as OrgRole)}
                  >
                    <option value="member">Member</option>
                    <option value="admin">Admin</option>
                  </select>
                  <button className="btn-primary shrink-0" disabled={inviting}>
                    {inviting ? <Loader2 className="h-4 w-4 animate-spin" /> : <UserPlus className="h-4 w-4" />}
                    Invite
                  </button>
                </form>
              )}
            </div>
          </>
        )}
      </main>
    </div>
  );
}
