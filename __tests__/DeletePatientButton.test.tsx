import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import DeletePatientButton from "@/app/DeletePatientButton";

jest.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: jest.fn(), push: jest.fn() }),
}));

describe("DeletePatientButton", () => {
  it("uses 'specimens' not 'samples' in confirmation message", async () => {
    const user = userEvent.setup();
    render(<DeletePatientButton id={1} name="LAB-2026-001" />);
    await user.click(screen.getByRole("button", { name: /delete/i }));
    const msg = screen.getByText(/specimens/i);
    expect(msg).toBeInTheDocument();
    expect(screen.queryByText(/samples/i)).not.toBeInTheDocument();
  });
});
