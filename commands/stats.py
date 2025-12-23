import requests

def query(spl):
    match spl[1]:
        case 'help':
            lines = [
                "wealth - a graph of the average rotur wealth over time",
                "rank_aura - lists the users with the most aura",
                "logins - a graph over time of all rotur logins",
                "store - the top downloaded and viewed apps on the store",
                "rank_logins - lists the users who have logged in the most",
                "credits - info about the economy's state"
            ]
            return "\n".join(lines)
        case 'rank_aura':
            val = requests.get('http://127.0.0.1:5602/stats/aura')
            data = val.json()
            result = "```\n"
            for user in data:
                result += f"{user['name']}: {user['aura']}\n"
            result += "```"
            return result
        case 'credits':
            val = requests.get('http://127.0.0.1:5602/stats/economy')
            data = val.json()
            result = (
                f"```\nAverage: {data['average']}\n"
                f"Total: {data['total']}\n"
                f"Variance: {data['variance']}\n"
                f"-- Currency Comparison --\n"
                f"Pence: {data['currency_comparison']['pence']}\n"
                f"Cents: {data['currency_comparison']['cents']}\n"
                "(This is NOT an exchange rate, purely intended as a comparison)```"
            )
            return result
        case 'store':
            val = requests.get('http://127.0.0.1:5601/stats')
            data = val.json()
            views = data.get('views', {})
            downloads = data.get('downloads', {})
            all_names = set(views) | set(downloads)
            filtered_names = [
                name for name in all_names
                if name in views and name in downloads
            ]
            sorted_names = sorted(
            filtered_names,
            key=lambda n: (-views.get(n, 0), n.lower())
            )
            max_name_len = max((len(name) for name in filtered_names), default=0)
            lines = []
            for name in sorted_names:
                v = views.get(name, 'undefined')
                d = downloads.get(name, 'undefined')
                lines.append(
                    f"{name.ljust(max_name_len)} {str(v).rjust(5)} views {str(d).rjust(7)} downloads"
                )
            result = "```\n" + "\n".join(lines) + "```"
            return result