"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { EmployeeTable } from "@/components/employees/employee-table";
import { EmployeeDialog } from "@/components/employees/employee-dialog";

export type Department = {
  id: string;
  name: string;
};

export type Role = {
  id: string;
  name: string;
};

export type Employee = {
  id: string;
  name: string;
  email: string;
  role: string;
  department_id: string;
  department_name: string;
  is_active: boolean;
  has_token: boolean;
  last_connected?: string;
  custom_role_id?: string;
  custom_role_name?: string;
};

export default function EmployeesPage() {
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editEmployee, setEditEmployee] = useState<Employee | null>(null);

  const loadEmployees = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api<Employee[]>("/api/employees");
      setEmployees(data);
    } catch {
      setEmployees([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadEmployees();
    api<Department[]>("/api/departments").then(setDepartments).catch(() => {});
    api<Role[]>("/api/roles").then(setRoles).catch(() => {});
  }, [loadEmployees]);

  const handleCreate = () => {
    setEditEmployee(null);
    setDialogOpen(true);
  };

  const handleEdit = (emp: Employee) => {
    setEditEmployee(emp);
    setDialogOpen(true);
  };

  return (
    <>
      <PageHeader
        title="Employees"
        description="Manage user accounts and MCP access tokens."
        action={
          <Button
            onClick={handleCreate}
            className="bg-primary text-primary-foreground hover:bg-primary/90"
          >
            <span className="material-symbols-outlined text-base mr-1">
              person_add
            </span>
            Add Employee
          </Button>
        }
      />

      <EmployeeTable
        employees={employees}
        loading={loading}
        onEdit={handleEdit}
        onRefresh={loadEmployees}
      />

      <EmployeeDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        employee={editEmployee}
        departments={departments}
        roles={roles}
        onSaved={loadEmployees}
      />
    </>
  );
}
