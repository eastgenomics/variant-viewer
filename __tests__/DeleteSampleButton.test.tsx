import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import DeleteSampleButton from "@/app/patients/[id]/DeleteSampleButton";

// Mock next/navigation
jest.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: jest.fn(), push: jest.fn() }),
}));

describe("DeleteSampleButton", () => {
  it('shows "Delete specimen" button text, not "Delete sample"', () => {
    render(
      <DeleteSampleButton id={1} name="SPEC_001" workflowStatus="pending" />
    );
    const btn = screen.getByRole("button");
    expect(btn).toHaveTextContent(/delete specimen/i);
    expect(btn).not.toHaveTextContent(/delete sample/i);
  });

  it("uses 'specimen' in confirmation message", async () => {
    const user = userEvent.setup();
    render(
      <DeleteSampleButton id={1} name="SPEC_001" workflowStatus="pending" />
    );
    await user.click(screen.getByRole("button", { name: /delete specimen/i }));
    const confirmText = screen.getByText(/spec_001/i);
    expect(confirmText.textContent).toMatch(/specimen/i);
    expect(confirmText.textContent).not.toMatch(/sample/i);
  });

  it("uses 'specimen' in high-risk confirmation for reported status", async () => {
    const user = userEvent.setup();
    render(
      <DeleteSampleButton id={1} name="SPEC_001" workflowStatus="reported" />
    );
    await user.click(screen.getByRole("button", { name: /delete specimen/i }));
    const msg = screen.getByText(/reported/i);
    expect(msg.textContent).toMatch(/specimen/i);
    expect(msg.textContent).not.toMatch(/sample/i);
  });
});
