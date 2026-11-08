import { createFileRoute } from "@tanstack/react-router";
import { EmployeeApp } from "@/components/employee/employee-app";

export const Route = createFileRoute("/employee")({
  head: () => ({
    meta: [
      { title: "Research — FINPILOT" },
      {
        name: "description",
        content: "Synthetic credit-research desk for a signed-in employee.",
      },
    ],
  }),
  component: EmployeePage,
});

function EmployeePage() {
  return <EmployeeApp />;
}
