import axios from "axios";

const API_BASE_URL =
    import.meta.env.VITE_API_BASE_URL ||
    "http://127.0.0.1:8000";

const dashboardApi = axios.create({
    baseURL: API_BASE_URL,
    timeout: 10000,
});

dashboardApi.interceptors.request.use(
    (config) => {
        const token =
            sessionStorage.getItem("access_token");

        if (token) {
            config.headers.Authorization =
                `Bearer ${token}`;
        }

        return config;
    },
    (error) => Promise.reject(error)
);


dashboardApi.interceptors.response.use(
    (response) => response,

    (error) => {
        if (
            error.response?.status === 401
        ) {
            sessionStorage.removeItem(
                "access_token"
            );
        }

        return Promise.reject(error);
    }
);


export async function fetchDashboardData() {
    const response = await dashboardApi.get(
        "/dashboard"
    );

    return response.data;
}