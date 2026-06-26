import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LoginPage } from "./LoginPage";

const navigateMock = vi.fn();
const loginMock = vi.fn();
const registerMock = vi.fn();
const joinWithInviteMock = vi.fn();

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => ({
    login: loginMock,
    register: registerMock,
    joinWithInvite: joinWithInviteMock,
  }),
}));

describe("LoginPage", () => {
  beforeEach(() => {
    navigateMock.mockReset();
    loginMock.mockReset();
    registerMock.mockReset();
    joinWithInviteMock.mockReset();
  });

  it("shows a friendly login error for missing accounts or wrong passwords", async () => {
    loginMock.mockRejectedValue(new Error("Login failed"));

    render(
      <MemoryRouter initialEntries={["/login"]}>
        <LoginPage />
      </MemoryRouter>
    );

    fireEvent.change(screen.getByLabelText("用户名"), { target: { value: "alice" } });
    fireEvent.change(screen.getByLabelText("密码"), { target: { value: "wrong-password" } });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));

    await waitFor(() => {
      expect(screen.getByText("账户不存在或密码错误")).toBeInTheDocument();
    });
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it("uses the same auth input styling for username and password fields", () => {
    render(
      <MemoryRouter initialEntries={["/login"]}>
        <LoginPage />
      </MemoryRouter>
    );

    expect(screen.getByLabelText("用户名")).toHaveClass("auth-input");
    expect(screen.getByLabelText("密码")).toHaveClass("auth-input");
  });

  it("renders Chinese copy for login and register modes", () => {
    render(
      <MemoryRouter initialEntries={["/login"]}>
        <LoginPage />
      </MemoryRouter>
    );

    expect(screen.getByRole("heading", { name: "登录" })).toBeInTheDocument();
    expect(screen.getByText("登录你的工作台")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "登录" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "去注册" }));

    expect(screen.getByRole("heading", { name: "注册" })).toBeInTheDocument();
    expect(screen.getByText("创建新账户")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "注册并进入" })).toBeInTheDocument();
    expect(screen.getByLabelText("显示名称（可选）")).toBeInTheDocument();
  });

  it("renders Chinese copy for invite join mode", () => {
    render(
      <MemoryRouter initialEntries={["/login?token=invite-demo"]}>
        <LoginPage />
      </MemoryRouter>
    );

    expect(screen.getByRole("heading", { name: "加入共享工作台" })).toBeInTheDocument();
    expect(screen.getByText("你收到了一个邀请，请设置用户名后加入。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "加入工作台" })).toBeInTheDocument();
  });

  it("shows a friendly register error for duplicate usernames", async () => {
    registerMock.mockRejectedValue(new Error("Username 'alice' is already taken"));

    render(
      <MemoryRouter initialEntries={["/login"]}>
        <LoginPage />
      </MemoryRouter>
    );

    fireEvent.click(screen.getByRole("button", { name: "去注册" }));
    fireEvent.change(screen.getByLabelText("用户名"), { target: { value: "alice" } });
    fireEvent.change(screen.getByLabelText("密码"), { target: { value: "secret123" } });
    fireEvent.click(screen.getByRole("button", { name: "注册并进入" }));

    await waitFor(() => {
      expect(screen.getByText("用户名已存在")).toBeInTheDocument();
    });
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it("shows a duplicate username error from api status even without a friendly message", async () => {
    const error = Object.assign(new Error("Conflict"), { status: 409, code: "conflict" });
    registerMock.mockRejectedValue(error);

    render(
      <MemoryRouter initialEntries={["/login"]}>
        <LoginPage />
      </MemoryRouter>
    );

    fireEvent.click(screen.getByRole("button", { name: "去注册" }));
    fireEvent.change(screen.getByLabelText("用户名"), { target: { value: "alice" } });
    fireEvent.change(screen.getByLabelText("密码"), { target: { value: "secret123" } });
    fireEvent.click(screen.getByRole("button", { name: "注册并进入" }));

    await waitFor(() => {
      expect(screen.getByText("用户名已存在")).toBeInTheDocument();
    });
  });
});
