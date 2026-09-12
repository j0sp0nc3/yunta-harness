namespace Yunta.Demo
{
    public interface IOrderProcessor
    {
        bool ProcessOrder(int orderId);
    }

    public class OrderService : IOrderProcessor
    {
        public bool ProcessOrder(int orderId)
        {
            return orderId > 0;
        }

        public async Task<int> CreateOrderAsync(string customerName)
        {
            await Task.Delay(10);
            return 101;
        }
    }
}
