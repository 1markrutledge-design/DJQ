import './globals.css';

export const metadata = {
    title: 'DJ Queue - Premium Song Request',
    description: 'Request songs at your favorite venues.',
};

export default function RootLayout({ children }) {
    return (
        <html lang="en">
            <body>{children}</body>
        </html>
    );
}
