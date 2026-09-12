export interface User {
    id: string;
    email: string;
}

export class UserService {
    async findUser(id: string): Promise<User | null> {
        return { id, email: "test@example.com" };
    }
}

export const formatUser = (user: User): str => {
    return `${user.id}: ${user.email}`;
};
