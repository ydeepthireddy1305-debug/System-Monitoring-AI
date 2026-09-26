import axios from "axios";

const API_BASE_URL =
    import.meta.env.VITE_API_BASE_URL ||
    "http://127.0.0.1:8000";

const authApi = axios.create({
    baseURL: API_BASE_URL,
    timeout: 10000,
});

export async function login(username, password) {
    const body = new URLSearchParams();

    body.append("username", username);
    body.append("password", password);

    const response = await authApi.post(
        "/auth/token",
        body,
        {
            headers: {
                "Content-Type":
                    "application/x-www-form-urlencoded",
            },
        }
    );

    sessionStorage.setItem(
        "access_token",
        response.data.access_token
    );

    return response.data;
}

export async function getCurrentUser() {
    const token =
        sessionStorage.getItem("access_token");

    if (!token) {
        throw new Error("Not authenticated");
    }

    const response = await authApi.get(
        "/auth/me",
        {
            headers: {
                Authorization: `Bearer ${token}`,
            },
        }
    );

    return response.data;
}

export function getAccessToken() {
    return sessionStorage.getItem(
        "access_token"
    );
}

export function logout() {
    sessionStorage.removeItem(
        "access_token"
    );
}