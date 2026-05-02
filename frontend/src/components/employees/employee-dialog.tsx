"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

type Department = { id: string; name: string };
type Role = { id: string; name: string };
type Employee = {
  id: string;
  name: string;
  email: string;
  role: string;
  department_id: string;
  custom_role_id?: string;
};

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  employee: Employee | null; // null = create mode
  departments: Department[];
  roles?: Role[];
  onSaved: () => void;
};

export function EmployeeDialog({
  open,
  onOpenChange,
  employee,
  departments,
  roles = [],
  onSaved,
}: Props) {
  const isEdit = !!employee;
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("employee");
  const [deptId, setDeptId] = useState("");
  const [customRoleId, setCustomRoleId] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (employee) {
      setName(employee.name);
      setEmail(employee.email);
      setRole(employee.role);
      setDeptId(employee.department_id);
      setCustomRoleId(employee.custom_role_id || "");
      setPassword("");
    } else {
      setName("");
      setEmail("");
      setPassword("");
      setRole("employee");
      setDeptId(departments[0]?.id || "");
      setCustomRoleId("");
    }
    setError("");
  }, [employee, open, departments]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError("");

    try {
      const body: Record<string, string | null> = {
        name,
        email,
        role,
        department_id: deptId,
        custom_role_id: customRoleId || null,
      };
      if (password) body.password = password;

      if (isEdit) {
        await api(`/api/employees/${employee.id}`, { method: "PUT", body });
      } else {
        if (!password) {
          setError("Password is required");
          setSaving(false);
          return;
        }
        await api("/api/employees", { method: "POST", body });
      }

      onSaved();
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-xl">
            {isEdit ? "Edit Employee" : "Add Employee"}
          </DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4 mt-2">
          <div className="flex flex-col gap-2">
            <Label htmlFor="emp-name">Name</Label>
            <Input
              id="emp-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className="bg-background"
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="emp-email">Email</Label>
            <Input
              id="emp-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="bg-background"
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="emp-password">
              Password {isEdit && "(leave blank to keep current)"}
            </Label>
            <Input
              id="emp-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={isEdit ? "••••••••" : "Min 8 characters"}
              className="bg-background"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-2">
              <Label>Role</Label>
              <Select value={role} onValueChange={(v) => v && setRole(v)}>
                <SelectTrigger className="bg-background">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="employee">Employee</SelectItem>
                  <SelectItem value="admin">Admin</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="flex flex-col gap-2">
              <Label>Department</Label>
              <Select value={deptId} onValueChange={(v) => v && setDeptId(v)}>
                <SelectTrigger className="bg-background">
                  <SelectValue placeholder="Select" />
                </SelectTrigger>
                <SelectContent>
                  {departments.map((d) => (
                    <SelectItem key={d.id} value={d.id}>
                      {d.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {roles.length > 0 && (
            <div className="flex flex-col gap-2">
              <Label>Custom Role</Label>
              <Select
                value={customRoleId || "__none__"}
                onValueChange={(v) => setCustomRoleId(v === "__none__" ? "" : (v ?? ""))}
              >
                <SelectTrigger className="bg-background">
                  <SelectValue placeholder="None" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">None</SelectItem>
                  {roles.map((r) => (
                    <SelectItem key={r.id} value={r.id}>
                      {r.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {error && (
            <p className="text-destructive text-sm bg-destructive/10 px-3 py-2 rounded-lg">
              {error}
            </p>
          )}

          <div className="flex justify-end gap-2 mt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={saving}
              className="bg-primary text-primary-foreground hover:bg-primary/90"
            >
              {saving ? "Saving..." : isEdit ? "Update" : "Create"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
