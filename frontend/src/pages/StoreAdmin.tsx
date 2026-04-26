import { Title, Text, Card, TextInput, Button, Table, TableHead, TableHeaderCell, TableBody, TableRow, TableCell } from "@tremor/react";

export default function StoreAdmin() {
  return (
    <div className="space-y-6 animate-in fade-in zoom-in duration-500">
      <div>
        <Title>Store Administration</Title>
        <Text>Manage pipeline mapping, physical camera settings, and access control.</Text>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Card>
              <Title>Add New Store</Title>
              <div className="space-y-4 mt-6">
                  <div>
                      <Text className="font-medium text-slate-700 block mb-1">Store ID</Text>
                      <TextInput placeholder="e.g. BLRJAY" />
                  </div>
                  <div>
                      <Text className="font-medium text-slate-700 block mb-1">Store Name</Text>
                      <TextInput placeholder="e.g. Jayanagar Outlet" />
                  </div>
                  <div>
                      <Text className="font-medium text-slate-700 block mb-1">Store Email (Access Mapping)</Text>
                      <TextInput placeholder="manager@jayanagar.com" />
                  </div>
                  <div>
                      <Text className="font-medium text-slate-700 block mb-1">Drive Folder URL</Text>
                      <TextInput placeholder="https://drive.google.com/..." />
                  </div>
                  <Button className="w-full mt-2">Register Store</Button>
              </div>
          </Card>
          
          <Card>
              <Title>Registered Configs</Title>
              <Text className="mt-2 text-sm text-slate-500">List populated via FastAPI DB endpoints.</Text>
              
              <Table className="mt-6">
                <TableHead>
                  <TableRow>
                    <TableHeaderCell>Store ID</TableHeaderCell>
                    <TableHeaderCell>Email Access</TableHeaderCell>
                    <TableHeaderCell>Drives Configured</TableHeaderCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                   <TableRow>
                     <TableCell>TEST_STORE_D07</TableCell>
                     <TableCell>admin@tester.com</TableCell>
                     <TableCell>Yes</TableCell>
                   </TableRow>
                </TableBody>
              </Table>
          </Card>
      </div>
    </div>
  );
}
