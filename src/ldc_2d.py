from sympy import Symbol, Eq, Ge, Abs, Function, Number
import sympy as sp
from modulus.pdes import PDES
from modulus.variables import Variables
import time
from modulus.solver import Solver
from modulus.dataset import TrainDomain, ValidationDomain
from modulus.data import Validation
from modulus.sympy_utils.functions import parabola
from modulus.sympy_utils.geometry_2d import Rectangle, Line
from modulus.csv_utils.csv_rw import csv_to_dict
from modulus.PDES.navier_stokes import NavierStokes, IntegralContinuity
from modulus.controller import ModulusController
import numpy as np
import math
import sys

def get_angle(theta, magnitude):
    # tan = math.tan(theta)
    # u = math.sqrt(1/(1+tan**2))
    # v = u*tan
    # return u*10, v*10
    # Baka Mitai ^^
    return math.cos(theta)*magnitude, math.sin(theta)*magnitude

class NavierStokes_2D(PDES):
    name = 'NavierStokes_2D'
    def __init__(self):
        # coordinates
        x, y = Symbol('x'), Symbol('y')

        # angle of attack
        alp = Symbol('alpha')
        
        # make input variables
        input_variables = {'x': x, 'y': y, 'alpha': alp}

        # velocity componets
        u = Function('u')(*input_variables)
        v = Function('v')(*input_variables)
        phi = Function('phi')(*input_variables)
        
        # How do we limit the range of alpha such that 10 - abs(alpha) >= 0?


        self.equations = Variables()
        # Here I implement a simpler form of a 2D Navier-Stokes equation in the form of laplacian(u,v) = 0 such that
        # laplacian(u,v).diff(u) = u and laplacian(u,v).diff(v) = v
        # laplacian(u,v).diff(t) = 0
        self.equations['x_alpha'] = u - 10*sp.cos(alp)
        self.equations['y_alpha'] = v - 10*sp.sin(alp)
        self.equations['x_component'] = u-phi.diff(x)
        self.equations['y_component'] = v-phi.diff(y)
        self.equations['NavierStokes_2D'] = (phi.diff(x)).diff(x) + (phi.diff(y)).diff(y) # grad^2(phi)


# params for domain
magnitude = 10
obstacle_length = 0.10
height = 6*obstacle_length  
# Honestly, we can set the height to anything as long 
# as the obstacle is always symmetric to the top and bottom of the domain. But for now, we will set it to a 
# multiple of the obstacle length.
width = 6*obstacle_length
# define geometry
rec = Rectangle((-width / 2, -height / 2), (width / 2, height / 2))
# rec.rotate(4 * (np.pi / 180))
obstacle = Line((0, 0), (0, obstacle_length), 1)
wake = Line((0, -3*obstacle_length), (0, 0), 1) # Wake to enforce kutta condition
obstacle.rotate(np.pi / 2)
wake.rotate(np.pi / 2)
# I rotate the line by 90 degrees to make it horizontal. 
# Now, the way this system is set up, the line will be positioned such that it is two units from the left of the rectangle, and 3 units 
# from its trailing edge. 

geo = rec

# define sympy varaibles to parametize domain curves
x, y = Symbol("x"), Symbol("y")
alp = Symbol("alpha")
# limit the range of alpha from -10 to 10 using np.pi.
alpha_range = {alp, (-np.pi*10/180, np.pi*10/180)}
# u, v = get_angle(alp, 10)
# u = float(sys.argv[1])
# v = float(sys.argv[2])
print(f"u = {alp}, v = {alp}")
time.sleep(1)

class LDCTrain(TrainDomain):
    def __init__(self, **config):
        super(LDCTrain, self).__init__()

#############################################################################################
        # I want to make the inlet velocity to be 10.0 m/s with an incidence angle of 4 degrees at the obstacle.
        # the inverse tan(v/u) gives me the required angle of incidence.
        # Drawing the scenario in comments below:
        #      +---------+
        #     /|/     \|/|
        #    //|// --- //|
        #   ///|/////////|
        #  ////+---------+
        #  //////////////
        #  / ////////////
        #    / //////////
        # where / is u + v such that tan-1(v/u) = x degrees(here i kept x as 4).

        inletBC = geo.boundary_bc(
            outvar_sympy={"u": sp.cos(alp)*magnitude, "v": sp.sin(alp)*magnitude},
            batch_size_per_area=1000,
            criteria=Eq(x, -width / 2),
            param_ranges = alpha_range
        )
        self.add(inletBC, name="Inlet")

        # outlet
        outletBC = geo.boundary_bc(
            outvar_sympy={"integral_continuity": u*height+v*width, "u": sp.cos(alp)*magnitude, "v": sp.sin(alp)*magnitude}, # Mimicing the far field conditions
            batch_size_per_area=256,
            criteria=Ge(y/height+x/width, 1/2),
            param_ranges = alpha_range
        )
        self.add(outletBC, name="Outlet")

        # bottomWall
        bottomWall = geo.boundary_bc(
            outvar_sympy={"u": sp.cos(alp)*magnitude, "v": sp.sin(alp)*magnitude},
            batch_size_per_area=1000,
            criteria=Eq(y, -height / 2),
            param_ranges = alpha_range
        )
        self.add(bottomWall, name="BottomWall")

        # obstacleLine
        obstacleLine = obstacle.boundary_bc(
            outvar_sympy={"u": sp.cos(alp)*magnitude, "v": 0},
            batch_size_per_area=1000,
            lambda_sympy={"lambda_u": 100, "lambda_v": 100},
        )
        self.add(obstacleLine, name="obstacleLine")

        # wakeLine
        # Here we define u = u and v = 0 at the trailing edge of the obstacle(which is at x=0, and v = v at x = right wall).
        l = lambda x : (x)/(3*obstacle_length) # x = 0 at the trailing edge of the obstacle
        wakeLine = wake.boundary_bc(
            outvar_sympy={"u": sp.cos(alp)*magnitude, "v": sp.sin(alp)*magnitude*l(x)},
            batch_size_per_area=1000,
            lambda_sympy={"lambda_u": 100, "lambda_v": 100},
            param_ranges = alpha_range
        )
        self.add(wakeLine, name="wakeLine")

        # interior
        interior = geo.interior_bc(
            outvar_sympy={"x_component": 0, "y_component": 0},
            bounds={x: (-width / 2, width / 2), y: (-height / 2, height / 2)},
            lambda_sympy={
                "lambda_continuity": 10,
                "lambda_x_component": geo.sdf,
                "lambda_y_component": geo.sdf,
            },
            batch_size_per_area=10000,
            param_ranges = alpha_range
        )
        self.add(interior, name="Interior")

        neighbourhood = geo.interior_bc(
            outvar_sympy={"x_component": 0, "y_component": 0},
            bounds={x: (-height / 3, height / 3), y: (-height / 8, height / 8)},
            lambda_sympy={
                "lambda_continuity": 100,
                "lambda_x_component": geo.sdf,
                "lambda_y_component": geo.sdf,
            },
            batch_size_per_area=10000,
            param_ranges = alpha_range
        )
        self.add(neighbourhood, name="Neighbourhood")


        # planes
       # plane1Cont = plane1.boundary_bc(
       #     outvar_sympy={"integral_continuity": 0.1333333},
       #     batch_size_per_area=256,
       #     lambda_sympy={"lambda_integral_continuity": 10},
       # )
       # plane2Cont = plane2.boundary_bc(
       #     outvar_sympy={"integral_continuity": 0.1333333},
       #     batch_size_per_area=256,
       #     lambda_sympy={"lambda_integral_continuity": 10},
       # )
       # plane3Cont = plane3.boundary_bc(
       #     outvar_sympy={"integral_continuity": 0.1333333},
       #     batch_size_per_area=256,
       #     lambda_sympy={"lambda_integral_continuity": 10},
       # )
       # plane4Cont = plane4.boundary_bc(
       #     outvar_sympy={"integral_continuity": 0.1333333},
       #     batch_size_per_area=256,
       #     lambda_sympy={"lambda_integral_continuity": 10},
       # )
       # plane5Cont = plane5.boundary_bc(
       #     outvar_sympy={"integral_continuity": 0.1333333},
       #     batch_size_per_area=256,
       #     lambda_sympy={"lambda_integral_continuity": 10},
       # )
       # plane6Cont = plane6.boundary_bc(
       #     outvar_sympy={"integral_continuity": 0.1333333},
       #     batch_size_per_area=256,
       #     lambda_sympy={"lambda_integral_continuity": 10},
       # )
       # plane7Cont = plane7.boundary_bc(
       #     outvar_sympy={"integral_continuity": 0.1333333},
       #     batch_size_per_area=256,
       #     lambda_sympy={"lambda_integral_continuity": 10},
       # )

       # self.add(plane1Cont, name="integralContinuity1")
       # self.add(plane2Cont, name="integralContinuity2")
       # self.add(plane3Cont, name="integralContinuity3")
       # self.add(plane4Cont, name="integralContinuity4")
       # self.add(plane5Cont, name="integralContinuity5")
       # self.add(plane6Cont, name="integralContinuity6")
       # self.add(plane7Cont, name="integralContinuity7")


# validation data
mapping = {"Points:0": "x", "Points:1": "y", "U:0": "u", "U:1": "v", "p": "p"}
openfoam_var = csv_to_dict("openfoam/cavity_uniformVel0.csv", mapping)
openfoam_var["x"] += -width / 2  # center OpenFoam data
openfoam_var["y"] += -height / 2  # center OpenFoam data
openfoam_invar_numpy = {
    key: value for key, value in openfoam_var.items() if key in ["x", "y"]
}
openfoam_outvar_numpy = {
    key: value for key, value in openfoam_var.items() if key in ["u", "v"]
}


class LDCVal(ValidationDomain):
    def __init__(self, **config):
        super(LDCVal, self).__init__()
        val = Validation.from_numpy(openfoam_invar_numpy, openfoam_outvar_numpy)
        self.add(val, name="Val")


class LDCSolver(Solver):
    train_domain = LDCTrain
    val_domain = LDCVal

    def __init__(self, **config):
        super(LDCSolver, self).__init__(**config)
        self.equations = (
            NavierStokes_2D().make_node() + IntegralContinuity().make_node()
        )
        flow_net = self.arch.make_node(
            name="flow_net", inputs=["x", "y", "alpha"], outputs=["u", "v", "phi"]
        )
        self.nets = [flow_net]

    @classmethod
    def update_defaults(cls, defaults):
        defaults.update(
            {
                "network_dir": "./network_checkpoint_ldc_2d",
                "decay_steps": 4000,
                "max_steps": 400000,
            }
        )


if __name__ == "__main__":
    ctr = ModulusController(LDCSolver)
    # ctr._config_parser._parser.add_argument('angle', metavar='A', type=float, nargs='+', help='angle')
    # vel = ctr._config_parser._parser.parse_args().angle[0]
    # print(vel)
    ctr.run()